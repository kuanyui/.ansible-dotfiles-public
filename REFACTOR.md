# REFACTOR backlog (do BEFORE new features)

Long-deferred cleanups, held until `ivm` stabilized. **Plan doc - record now,
execute one phase at a time, a commit (or a few) per phase, finish + verify one
before starting the next.** NOT one mega-commit.

Order: the pure renames first (they touch the most files; doing them up front
means everything after is written against the final names), then the functional
shared-assets work, then the container engine.

Companion docs: `roles/quickemu_vm/TODO.md`, `roles/incus_vm/REDESIGN.md`,
`roles/container_apps/REDESIGN.md`.

---

## Progress

Durable, git-tracked tracker (the in-session task tool is ephemeral / not
committed - use it only for the fine-grained steps WHILE executing a phase).
Tick a box when the phase is finished + verified + committed.

- [x] Phase 0a - `provision_*` registry role rename
- [x] Phase 0b - `vm_*` role rename (commands stay `ivm`/`qvm`/`pvm`)
- [x] Phase 0c - `essentials` Makefile targets
- [x] Phase 0d - split `roles/dotfiles` -> `bash` + `tmux`
- [x] Phase 0e - retire `setup_*` gates / config-model cleanup
- [x] Phase 1 - shared assets foundation (`__common__`, `_shared_prebuilt_provision_assets`, `ivm` consumes)
- [x] Phase 2 - `qvm provision`
- [ ] Phase 3 - `pvm` / container engine

---

## Naming decisions (LOCKED)

Two themes: (a) the launcher ROLES become a `vm_*` family so they sort together
in `roles/` (the commands STAY `ivm`/`qvm`/`pvm` - see note below); (b) the two
provisioning-registry roles get a shared `provision_` prefix so the siblings sort
together.

| concern | old | new |
| --- | --- | --- |
| launcher role dir | `roles/incus_vm` | `roles/vm_incus` |
| launcher role dir | `roles/quickemu_vm` | `roles/vm_quickemu` |
| launcher role dir | (new, Phase 3) | `roles/vm_podman` |
| ansible-managed subdir | `incus-vm/` | `vm-incus/` |
| ansible-managed subdir | `quickemu-vm/` | `vm-quickemu/` |
| setup gate | `setup_incus_vm` | `setup_vm_incus` |
| setup gate | `setup_quickemu_vm` | `setup_vm_quickemu` |
| Makefile targets | `incus-*` / `quickemu-*` | `vm-incus-*` / `vm-quickemu-*` |
| registry role dir | `roles/distro_packages` | `roles/provision_distro_packages` |
| registry role dir | `roles/thirdparty_software` | `roles/provision_thirdparty_software` |
| registry vars (role `defaults/`) | `distro_packages_*` / `thirdparty_software_*` | `provision_distro_packages_*` / `provision_thirdparty_software_*` |
| install gates (`group_vars/`) | `distro_packages_install_*` | `provision_distro_packages_install_*` |
| config role split | `roles/dotfiles` (bash+tmux grab-bag) | `roles/bash` + `roles/tmux` |
| essentials targets | `apply-{user,root,all-users}` / `check-*` | `apply-essentials-{user,root,all-users}` / `check-essentials-*` |
| config role rename | `roles/local_pkgs` | `roles/local_lang_pkg_managers` |
| its managed dir | `~/.local-pkgs/` | `~/.local-lang-pkg-managers/` (hyphens = path convention, vs the underscore role dir; no migration - role never run) |

**Commands (and on-VM data) are UNCHANGED - only role-level names move.** The
binaries stay `ivm` / `qvm` / `pvm`, as do their env vars (`IVM_ROOT` / `QVM_HOME`),
completions, inner data dirs (`vm-incus/ivm/`), and crucially every identifier
PERSISTED on real VMs: the `user.ivm_*` tags (cwd binding etc.) and the
`ivm_mount_*` / `ivm_shadow_*` device names. Keeping the command name `ivm` is
exactly what makes those stay self-consistent, so there is NO VM migration / no
back-compat shim. The only thing forgone vs renaming commands to `vm*` is `vm<TAB>`
grouping - judged not worth the migration (and `ivm` = "incus vm" reads fine).
The role dir `vm_incus` installing a command named `ivm` is a deliberate, normal
package-name != binary-name split. Revisit a command rename later only if wanted.

**Why the registry vars MUST rename (not just cosmetics):** ansible-lint
`var-naming[no-role-prefix]` - "Variables names from within roles should use
`role_name_` as a prefix" (docs.ansible.com/projects/lint/rules/var-naming/).
Renaming the role dir without renaming its `defaults/` vars would TRIP this rule.
Scope nuance: the rule covers variables defined in a role's `defaults/`+`vars/`
(the registry bundles) - so those are lint-REQUIRED to rename; the install gates
live in `group_vars/all.yml`, which the rule does NOT cover, so renaming THOSE is
a consistency choice (breaks any existing host_vars/group_vars that set them -
acceptable: the user's own config).

**Launcher binary `pvm` (podman) is NOT a VM by default** - keep the
container-honest description (`pvm - podman container launcher (rootless;
optional libkrun microVM)`); the `vm` prefix is the family label, the help text
carries the honesty. See Phase 3 guardrails. (Supersedes the `capp`/`cax`/`coci`
working name in `container_apps/REDESIGN.md`: `s/capp/pvm/` when Phase 3 starts.)

---

## Functional goal (Phases 1-3)

`provision_distro_packages` + `provision_thirdparty_software` + the guest
dotfiles become ONE source of truth, consumed by every provisioning backend: the
host, `ivm` guests, `qvm` guests, and `pvm` containers. Today only the host
(directly) and `ivm` (via a hand-maintained JSON render) consume them.

### Target: one shared, regenerable asset dir

- **Producer role:** `roles/_shared_prebuilt_provision_assets` (leading `_` =
  internal, `include_role`-only, no playbook/Makefile target).
- **Output:** `~/.local/share/ansible-managed/shared-prebuilt-provision-assets/`

```
shared-prebuilt-provision-assets/
  distro-package-groups.json   # { <feature>: { __common__:[...], Debian:[...], Suse:[...], RedHat:[...] } }
  thirdparty-software.json     # same key scheme
  dotfiles/
    <feature>/                 # zsh, bash, emacs, mpv, ...   (feature name == JSON key where it overlaps)
      __common__/{root,home/user}/
      Debian/{root,home/user}/
      Suse/{root,home/user}/
      RedHat/{root,home/user}/
```

- **Unified key scheme everywhere:** `__common__` (always-applied bucket) + the
  exact `ansible_os_family` values `Debian`/`Suse`/`RedHat`. Kills the current
  lowercase-`common/debian/...` vs Capitalized-`rootfs/Debian/...` split and lets
  `ivm` drop its `ANSIBLE_OS_FAMILY_TO_OVERLAY_KEY` map (family value IS the key).
- **Feature-first dotfiles** (decided over family-first / tool-matrix):
  `provision <feature>` = install `json[feature]` pkgs + run `thirdparty[feature]`
  recipe + `cp dotfiles/<feature>/__common__` then `.../<distro>` (two copies,
  distro overlays common). Selective by construction (skip emacs; add mpv later =
  one new top dir). A feature may have only some sides (`basic_tools` = pkgs only).
- **Removes the `config-files/` special case:** emacs config becomes
  `dotfiles/emacs/__common__/home/user/.emacs.d`.

### Three consumption models (same assets, different mechanics)

| Consumer | When | How | Status |
| --- | --- | --- | --- |
| host | ansible apply | reads the registry VARS directly (no JSON) | done |
| `ivm` | runtime, in guest | JSON + cp dotfiles; install via `incus exec` | done (migrate to shared dir) |
| `qvm` | runtime, in guest | JSON + push dotfiles; install via QGA `guest-exec` | to build (`qvm provision`) |
| `pvm` | build time, in image | `Dockerfile` reads the assets at image build | not started; apt-only today |

Source of truth stays the role `defaults/`; the JSON is only a serialization for
the non-ansible consumers.

---

## Phases (each: finish -> verify -> commit, then next)

### Phase 0a - `provision_*` registry role rename

Rename `roles/distro_packages` -> `roles/provision_distro_packages` and
`roles/thirdparty_software` -> `roles/provision_thirdparty_software`; rename their
`defaults/` vars to match (lint-required); rename the `group_vars` install gates
for consistency. Update every reference: playbooks, Makefile, `group_vars/all.yml`,
the `ivm` `include_vars` path + render-dict VALUES, the new shared role.

Verify: `grep` old names == 0; `ansible-lint` clean on the two roles;
`ansible-playbook --syntax-check`; a host `apply` still installs the same packages.

### Phase 0b - `vm_*` role rename (ROLE-LEVEL ONLY; commands unchanged)

Rename ONLY the `incus_vm` / `quickemu_vm` ROLE token (a distinctive token - no
3-letter `ivm` ambiguity, no `user.ivm_*` collision):

- `roles/incus_vm` -> `roles/vm_incus`, `roles/quickemu_vm` -> `roles/vm_quickemu`
- role-internal vars `incus_vm_*` -> `vm_incus_*` (21, incl. the `incus_vm_uninstall_*`
  teardown toggles; `incus_vm_ivm_dir` -> `vm_incus_ivm_dir` - the `ivm` part STAYS)
  and `quickemu_vm_*` -> `vm_quickemu_*` (6) - lint var-naming[no-role-prefix]
- ansible-managed subdirs `incus-vm/` -> `vm-incus/`, `quickemu-vm/` -> `vm-quickemu/`
  (the inner `ivm/` / `qvm` command-data dirs STAY)
- `setup_incus_vm` -> `setup_vm_incus`, `setup_quickemu_vm` -> `setup_vm_quickemu`
- Makefile targets `incus-*` -> `vm-incus-*`, `quickemu-*` -> `vm-quickemu-*`;
  var `INCUS_VM_HOST_TEARDOWN_*` -> `VM_INCUS_HOST_TEARDOWN_*`
- playbook files `incus_vm.yml`/`incus_vm_uninstall.yml` -> `vm_incus.yml`/...;
  `quickemu_vm*.yml` -> `vm_quickemu*.yml`
- docs/READMEs

NOT touched (commands + persisted data, per the Naming note): `ivm`/`qvm` binaries,
`files/ivm`/`files/qvm`, completions `_ivm`/`ivm.bash`/etc., `IVM_ROOT`/`QVM_HOME`,
the inner `ivm/`/`qvm` dirs, and ALL `user.ivm_*` tags + `ivm_mount_*`/`ivm_shadow_*`
device names. `incus_storage_pool*` vars + the `incus_storage_pool.py` script also
stay (Option A) - and all incus-PRODUCT tokens (`incus.service`, `incusbr0`, etc.).
So NO `s/incus/.../`, NO `s/ivm/.../` - only the `incus_vm`/`quickemu_vm` tokens move.

Verify: `grep` for `incus_vm`/`quickemu_vm` (the role token) == 0 in functional
files; `user.ivm_*` / `ivm_mount_` / `ivm_shadow_` / `IVM_ROOT` still present
(unchanged); both playbooks `--syntax-check`; completions `zsh -n`/`bash -n`;
`ivm --help` / `qvm --help` run; unit tests pass.

### Phase 0c - `essentials` Makefile-target rename

`apply-{user,root,all-users}` -> `apply-essentials-{user,root,all-users}` (+ the
`check-*` dry-run parallels; `sandbox-{user,root}` similarly). Names the base
user/root provisioning ("essentials" = bash/tmux/zsh/emacs dotfiles), distinct
from the specific `apply-apparmor` / `vm-incus-*` / ... targets. Pure Makefile
rename (+ `.PHONY`, `make help`). Sub-decision: targets only (lean), OR also
rename the playbooks `user.yml`/`root.yml`/`all.yml` -> `essentials_*.yml` (more
churn: README playbook tree). Tradeoff: the renamed targets are longer to type
for the most common daily command.

Verify: `make -n` the new targets; `make help`; `grep` old target names == 0.

### Phase 0d - split `roles/dotfiles` -> `roles/bash` + `roles/tmux`

`roles/dotfiles` is a vague grab-bag holding exactly `.bashrc.j2` (bash) +
`.tmux.conf` (tmux) behind a generic glob-and-deploy. Split into two explicit
config-only roles (consistent with the per-tool `roles/zsh` / `roles/emacs`):
`roles/bash` deploys `.bashrc` (keeps the `is_root` branch), `roles/tmux` deploys
`.tmux.conf` (static, no `is_root`). Drop the generic find/loop for one explicit
deploy each (net simpler). Update the 3 consumers: `playbooks/user.yml`,
`playbooks/root.yml`, and `vm_incus`'s `_stage_family.yml`. (tmux the PACKAGE
already comes from `basic_tools`; these roles are config-only.) RESOLVES the
Phase 1 feature-first open detail - `dotfiles/bash/` + `dotfiles/tmux/` fall out
naturally.

Verify: host `apply` still drops `.bashrc` + `.tmux.conf` for user AND root;
`grep -r 'name: dotfiles'` == 0; syntax-check.

### Phase 0e - retire `setup_*` gates; roles own their vars; playbooks select roles

The gate pattern is cruft at this scale: `setup_zsh` is already DEAD (declared in
group_vars, consumed nowhere); every optional role BOTH self-gates
(`when: setup_X`) AND has its own dedicated playbook + Makefile target - two
switches for one feature. Replace it with explicit role selection.

Two kinds of var are currently mixed in `group_vars/all.yml`:

- **on/off gates** (`setup_apparmor` / `setup_vm_incus` / `setup_mpv` / ... incl. the
  dead `setup_zsh`) -> DELETE, plus each role's self-skip preamble AND apparmor's
  scattered mid-task `when: setup_apparmor` (5 occurrences in its main.yml).
- **genuine config** -> MOVE into the owning role's `defaults/`: `has_gui_support`,
  `provision_distro_packages_install_*` (bundle selection),
  `podman_runtime` / `podman_runtime_scope` (-> `podman_oci_runtimes`; note
  `setup_podman_oci_runtimes` is already duplicated in that role's defaults).
  group_vars overrides only when a host differs from the default.

Model (confirmed - Option A): **optional features ONLY via their dedicated
playbook / Makefile target.** NO per-host selection machinery in THIS repo - it is
public; large-scale/multi-host deployment belongs in a SEPARATE PRIVATE ansible
project with hardcoded hostnames (keeps hostnames out of this public repo). The
dedicated playbooks drop their `setup_X: true` bypass line (just list the role).

essentials playbooks (`user.yml`/`root.yml`, Phase 0c) list always-on roles
directly: `zsh`, `emacs`, `bash`, `tmux`. ALL optional roles are REMOVED from
`user.yml`.

`roles/local_pkgs` -> `roles/local_lang_pkg_managers` (its managed tree
`~/.local-pkgs/` -> `~/.local-lang-pkg-managers/` - hyphenated path vs the
underscore role dir, matching the `incus_vm` <-> `incus-vm/` convention; NO
migration/idempotence needed - the role has never been run). It stays OPT-IN, NOT in essentials (the
user does not want the npm/pip/pipx/cargo/go global-install redirect always-on),
so it gains its OWN dedicated playbook + Makefile target (it has none today).
Bonus: out of essentials, its old "must run FIRST" ordering coupling disappears.

Result: `group_vars/all.yml` shrinks from ~25 lines to just genuine cross-role
config (the `shared_*` template fragments, maybe `has_gui_support`).

Verify: `grep -rn 'setup_'` across roles/playbooks/group_vars finds none of the
deleted gates; `apply-essentials-*` deploys the same essentials; each optional
target still works standalone; syntax-check; ansible-lint.

### Phase 1 - shared assets foundation (`ivm` behavior preserved)

1. Rename keys to `__common__` + `Debian/Suse/RedHat` across the registry defaults
   + every consumer.
2. Build `roles/_shared_prebuilt_provision_assets`: render both JSONs (the only
   place that lists feature keys) + stage the feature-first dotfiles tree
   (absorbing `vm_incus`'s `stage_dotfiles.yml`/`_stage_family.yml` + the emacs
   `config-files` case as `dotfiles/emacs/__common__/`).
3. `vm_incus` consumes the shared dir; `ivm` reads from it and pushes per-feature
   (`__common__` + `<distro>`).
4. CLAUDE.md amendment (below).

Verify: `ivm env`/`--dry-run` resolves identical package lists pre/post; JSONs
equivalent modulo key rename; syntax-check; `ivm` unit tests green; fresh apply
produces the new dir; real-host `ivm init` (host-only).

### Phase 2 - `qvm` consumes the registry + `qvm provision`

`roles/vm_quickemu` includes the shared role; `qvm provision <feature...>` reads
the JSON, resolves `__common__` + the VM's recorded distro family, installs via
QGA `guest-exec`, runs `thirdparty[feature]` recipes, pushes
`dotfiles/<feature>/{__common__,<distro>}`. Resolves the base-box question:
`qvm init <distro>` + optional `--provision basic_tools`.

Verify: `qvm provision --dry-run`; resolver unit tests; real-host QGA run.

### Phase 3 - `pvm` / container engine (== `container_apps/REDESIGN.md`)

Fold `container_templates` + `container_apps` into ONE engine (`pvm`, role
`vm_podman`) that reads declarative templates, and have its image build consume
the shared assets: `Dockerfile` reads `distro-package-groups.json` (decide:
keep apt-only vs generalize per-family) + `COPY dotfiles/<feature>/{__common__,<distro>}`.

**Ordering:** after Phase 1 (capp must consume the reshaped feature-first +
`__common__` dotfiles, not the old per-family `rootfs/`).

**Isolation guardrails (the `vm` name must be EARNED):** the default runtime
(crun/namespaces) is shared-HOST-kernel - the boundary `ivm` exists to avoid. So
`pvm` steers to the VM-grade runtime:

- **install-time, on Linux:** warn that a shared-kernel container is weaker than a
  real VM - for kernel isolation use `ivm`; if using `pvm`, prefer `libkrun`.
- **`pvm init`, on Linux, runtime != `libkrun`** (crun/runc): an interactive
  `[y/N]` confirm gate (default No), **strongly not recommended**; `--yes`
  bypasses, non-TTY without `--yes` aborts.
- **every later run of a non-libkrun container** (`start`/`exec`/`shell`/...):
  PRINT the warning each time, non-blocking (the gate already happened at `init`).

Scope: a Linux / native-podman concern (shared kernel = HOST's). On macOS/Windows
podman runs inside a `podman machine` VM, so a non-libkrun runtime there shares
only that VM's kernel - the run-time warning can soften/skip there.

---

## Open details to settle during execution

- **feature != role name, 1:N.** RESOLVED by Phase 0d: splitting `roles/dotfiles`
  into `roles/bash` + `roles/tmux` makes each a clean per-tool feature (zsh/emacs
  already are). So Phase 1's feature dirs map 1:1 to per-tool roles.
- **Which dotfiles are `__common__` vs family-specific** - audit per file
  (`.zshrc` = family, via `override_os_family`; `.emacs.d`/`.tmux.conf`/`.bashrc`
  likely `__common__` - confirm).
- **`user` vs `root` variants** stay (`is_root` render differs) - keep the
  `{root,home/user}` split per feature.
- **Makefile target form** - `vm-incus-install` (matches role dir) chosen.

## Deferred / out of scope (recorded so it is not re-derived)

- **`podman_oci_runtimes` rethink (deferred; user unused).** Considered: fold into
  `vm_podman` as `tasks/` (e.g. `oci_runtime_krun`, or fetch a gvisor binary), and
  DROP the "default runtime" concept entirely - setting a default runtime is
  impractical (`krun` has poor compatibility with existing container images); the
  role should just INSTALL a runtime, not make it the default. **Not doing it
  now:** the user uses neither `krun` nor gvisor, and a heavier kata path is not
  worth a role. **Its `setup_podman_oci_runtimes` gate was KEPT** (the ONE role 0e
  did not de-gate) - its gate is woven through compound `when:`s + task names, and
  retiring it belongs with this rethink. The gate now lives only in the role's
  `defaults/` (+ the dedicated playbook's bypass), no longer in group_vars.
  (`podman_runtime`/`podman_runtime_scope` were already in the role `defaults/`;
  0e only dropped the group_vars `libkrun` override, so the default reverts to
  `default` - aligned with "don't force a runtime".)

## CLAUDE.md amendment (Phase 1) - APPLIED

The namespace rule ("every face role owns exactly one hyphenated subdir; utility
roles must NOT own a top-level subdir") has no slot for a dir SHARED by multiple
face roles. Add a third category:

> **Shared prebuilt-asset dirs.** A top-level subdir owned by an internal
> `_`-prefixed producer role and consumed by several face roles (e.g.
> `shared-prebuilt-provision-assets/`, produced by
> `roles/_shared_prebuilt_provision_assets`). It is a REGENERABLE cache: any
> consumer's apply rebuilds it; it holds no unique state. Lifecycle: not removed
> by any single consumer's uninstall (others may still need it); a dedicated
> cleanup removes it. The only sanctioned exception to "utility roles don't own a
> top-level subdir".
