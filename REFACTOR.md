# REFACTOR: one shared provision-assets registry (host / ivm / qvm / podman)

Plan doc. **No code yet** - this is the agreed architecture + phased order to
execute against. Companion trackers: `roles/quickemu_vm/TODO.md` (qvm),
`roles/incus_vm/REDESIGN.md`, `roles/container_apps/REDESIGN.md` (the capp engine
the podman phase tangles with).

## Goal

`distro_packages` + `thirdparty_software` + the guest dotfiles are ONE source of
truth, consumed by every backend that provisions a machine: the host, ivm
guests, qvm guests, and (eventually) podman containers. Today only the host
(directly) and ivm (via a hand-maintained JSON render) consume them; qvm and
podman don't.

## Why now (current pain)

- **The JSON render is hand-listed in one consumer.** `roles/incus_vm/tasks/ivm_install.yml`
  spells out 14 package-group keys + 4 thirdparty keys into two `copy` tasks. qvm
  and podman would each have to copy that - it must move somewhere shared.
- **Two key-casing conventions collide.** The registry vars use `common` +
  lowercase `debian/suse/redhat` (`roles/distro_packages/defaults/main.yml`); the
  staged rootfs uses Capitalized `Debian/Suse/RedHat` (the real `ansible_os_family`
  values). ivm carries an `ANSIBLE_OS_FAMILY_TO_OVERLAY_KEY` map (`Debian`->`debian`)
  just to bridge them.
- **A `config-files/` special case.** Emacs config is distro-independent, so it is
  staged once outside the per-family `rootfs/` tree - a one-off shape that does not
  generalize to the next distro-independent config (mpv, qtcreator, ...).
- **Dotfiles staging is welded into ivm.** `stage_dotfiles.yml` + `_stage_family.yml`
  live in `roles/incus_vm`; qvm/podman need the same staged trees.

## Target architecture

One internal utility role produces one shared, regenerable output dir; every
backend consumes from it.

- **Role:** `roles/_shared_prebuilt_provision_assets` (leading `_` = internal,
  `include_role`-only, no playbook, no Makefile target).
- **Output dir:** `~/.local/share/ansible-managed/shared-prebuilt-provision-assets/`

```
shared-prebuilt-provision-assets/
  distro-package-groups.json   # { <feature>: { __common__:[...], Debian:[...], Suse:[...], RedHat:[...] } }
  thirdparty-software.json     # { <feature>: { __common__:"...", Debian:"...", ... } }   (same key scheme)
  dotfiles/
    <feature>/                 # zsh, bash, emacs, mpv, ...   (feature name == JSON key where it overlaps)
      __common__/{root,home/user}/
      Debian/{root,home/user}/
      Suse/{root,home/user}/
      RedHat/{root,home/user}/
```

**Unified key scheme everywhere** (both JSONs + the dotfiles dirs):
`__common__` (the always-applied bucket) + the exact `ansible_os_family` values
`Debian` / `Suse` / `RedHat`. This kills the lowercase-vs-Capitalized split and
lets ivm drop `ANSIBLE_OS_FAMILY_TO_OVERLAY_KEY` (family value IS the key).

**Feature-first dotfiles** (decided over family-first / tool x distro nesting):
a "feature" is the provisioning unit. `provision <feature>` =
`install json[feature] packages` + `run thirdparty[feature] recipe` +
`cp dotfiles/<feature>/__common__` then `cp dotfiles/<feature>/<distro>` (two
copies, distro-overlay-on-common). A feature may have only some sides
(`basic_tools` = packages only; `claude` = recipe only; `emacs` = packages +
config). Selective by construction (skip emacs where unwanted; add mpv later =
one new top dir). Overlay precedence: `<distro>` wins over `__common__` on a
path collision (rare - a file is usually wholly common OR wholly family-specific).

**The `config-files/` special case is removed**: emacs config becomes
`dotfiles/emacs/__common__/home/user/.emacs.d`.

## Three consumption models (same assets, different mechanics)

| Consumer | When | How | Status |
|---|---|---|---|
| host | ansible apply | reads the registry VARS directly (no JSON) | done (`roles/distro_packages`) |
| ivm | runtime, in guest | reads the JSON + cp dotfiles; installs via `incus exec` | done (migrate to the shared dir) |
| qvm | runtime, in guest | reads the JSON + push dotfiles; installs via QGA `guest-exec` | to build (`qvm provision`) |
| podman | build time, in image | `Dockerfile` reads the assets at image build | not started; apt-only today |

Source of truth stays the role `defaults/` (host reads them live); the JSON is
only a serialization for the non-ansible consumers (guests/containers).

## Impact / ripple list for the `__common__` + casing change

- `roles/distro_packages/defaults/main.yml` - every bundle's `common` ->
  `__common__`, `debian/suse/redhat` -> `Debian/Suse/RedHat`.
- `roles/thirdparty_software/defaults/main.yml` - same.
- `roles/distro_packages/tasks/main.yml` - `map(attribute='common')` ->
  `'__common__'`; `selectattr('debian'|'suse'|'redhat', ...)` -> Capitalized.
- `roles/_install_distro_packages` - already keyed Capitalized (`Debian/Suse/RedHat`);
  audit for any `common` use.
- `roles/incus_vm/files/ivm` - drop `ANSIBLE_OS_FAMILY_TO_OVERLAY_KEY`; `resolve_group`
  reads `__common__` + the family value directly. Update its tests.
- `roles/incus_vm/tasks/ivm_install.yml` - remove the two hand-listed render tasks
  (move into the shared role) and the `config-files/emacs` staging.
- `roles/incus_vm/tasks/stage_dotfiles.yml` + `_stage_family.yml` - move into the
  shared role and re-shape from `rootfs/<family>/{home/user,root}` to
  `dotfiles/<feature>/{__common__,<family>}/{root,home/user}`.
- `roles/incus_vm/files/ivm` push path - push per requested feature
  (`__common__` then `<distro>`) instead of one merged `rootfs/<family>` tree.

Note: the casing change is a net SIMPLIFICATION for ivm (one fewer map).

## Open details to settle in Phase 1

- **feature != role name, 1:N.** `roles/dotfiles` currently renders bash + tmux
  together into one `target_home`. Feature-first wants `dotfiles/bash/` and
  `dotfiles/tmux/` separable - decide: split the role's staging per feature, OR
  keep a coarser feature (e.g. one `shell_base` feature) for the dotfiles role's
  bundle. zsh is its own role (`.zshrc`, family-specific via `override_os_family`);
  emacs is its own role (common).
- **Which dotfiles are `__common__` vs family-specific** - audit per file
  (`.zshrc` = family; `.emacs.d`, `.tmux.conf`, `.bashrc` likely common - confirm).
- **`user` vs `root` variants** stay (`is_root` render differs: root prompt, no
  redundant sudo) - keep the `{root,home/user}` split per feature.

## Phased plan

### Phase 1 - structure + naming refactor (foundation; ivm behavior preserved)

1. Rename keys to `__common__` + `Debian/Suse/RedHat` across the registry defaults
   + every consumer (ripple list above).
2. Create `roles/_shared_prebuilt_provision_assets`: render both JSONs (the only
   place that lists feature keys) + stage the feature-first dotfiles tree
   (absorbing `stage_dotfiles.yml`/`_stage_family.yml` + the emacs `config-files`
   case as `dotfiles/emacs/__common__/`).
3. ivm consumes the shared dir: `include_role` the new role; `ivm` reads from
   `shared-prebuilt-provision-assets/` and pushes per-feature (`__common__` +
   `<distro>`).
4. CLAUDE.md amendment (below).

Verify: `ivm env`/`--dry-run` resolves identical package lists pre/post; both
JSONs equivalent modulo key rename; `ansible-playbook --syntax-check`; ivm unit
tests green; a fresh apply produces the new dir; real-host `ivm init` (host-only).

### Phase 2 - qvm consumes the registry + `qvm provision`

1. `roles/quickemu_vm` `include_role`s `_shared_prebuilt_provision_assets`.
2. `qvm provision <feature...>`: read the JSON, resolve `__common__` + the VM's
   recorded distro family, install via QGA `guest-exec` (apt/zypper/dnf); run
   `thirdparty[feature]` recipes; push `dotfiles/<feature>/{__common__,<distro>}`.
3. Resolves the base-template question: `qvm init <distro>` +
   (optional `--provision basic_tools`).

Verify: `qvm provision --dry-run`; unit tests for the resolver; real-host QGA run
(TW first-boot agent, then `qvm provision basic_tools`).

### Phase 3 - podman consumes the assets == the container-engine redesign

This is NOT separate work bolted on - it IS the already-planned engine redesign
in `roles/container_apps/REDESIGN.md`: fold `container_templates` +
`container_apps` into ONE engine (working name `capp`; final TBD `capp`/`cax`/`coci`)
that reads declarative templates, and have its image build consume the shared
assets:

- packages: the `Dockerfile` build step reads `distro-package-groups.json` (today
  it hardcodes an apt-only list - decide: keep apt-only, or generalize per-family).
- dotfiles: `COPY dotfiles/<feature>/{__common__,<distro>}` into the image at
  build time (REDESIGN already says "reuse `roles/zsh`, stage like ivm").

**Ordering: AFTER Phase 1, not before.** capp will consume the dotfiles structure
Phase 1 reshapes (feature-first + `__common__`). Building capp first would bind it
to the old per-family `rootfs/`, forcing rework. So Phase 1 is the prerequisite;
the capp build then subsumes this phase.

**Naming: `pvm`** (decided - family consistency wins). The launcher family is
`ivm` (incus) / `qvm` (quickemu) / `pvm` (podman); the parallel `p`+`vm` name is
what stays memorable, weighted above taxonomic purity. The `vm` suffix has a real
basis here: the repo ships the `libkrun` runtime option (`podman_runtime: libkrun`),
a per-container microVM, and on macOS/Windows podman runs via a `podman machine`
Linux VM. CAVEAT so the name does not deceive: podman's DEFAULT is namespaces, not
a VM, so the one-line description / `pvm --help` / README first line MUST say it
plainly, e.g. `pvm - podman container launcher (rootless; optional libkrun microVM)`.
The name is the memorable family label; the help text carries the honesty.
(Supersedes the `capp`/`cax`/`coci` working name in `roles/container_apps/REDESIGN.md`
- do the `s/capp/pvm/` there when that redesign actually starts.)

**pvm isolation guardrails (the `vm` name must be EARNED, not assumed).** The
default runtime (crun / namespaces) is shared-HOST-kernel - exactly the boundary
the user rejects (the reason `ivm` exists). So pvm actively steers to the
VM-grade runtime with two warnings:

- **install-time, on Linux:** warn that a shared-kernel container is weaker
  isolation than a real VM - for kernel isolation use `ivm`; if using pvm,
  prefer the `libkrun` runtime.
- **`pvm init`, on Linux, when the chosen runtime is NOT `libkrun`** (crun /
  runc): an interactive `[y/N]` confirm gate - **strongly not recommended** (the
  container shares the host kernel; kernel attack surface), pointing at `libkrun`
  or `ivm`. `--yes` bypasses (automation); non-TTY without `--yes` aborts. (Default
  No, because the action is discouraged - the user wrote `Y/n`; flip to default-Yes
  if preferred.)
- **every later run of a non-libkrun container** (`start` / `exec` / `shell` /
  ...): PRINT the same warning each time, non-blocking - a standing reminder, no
  prompt (the gate already happened at `init`).

A `libkrun` runtime gets neither the prompt nor the nag (see Scope below for the
macOS/Windows case).

Scope: this is a Linux / native-podman concern (the shared kernel is the HOST's).
On macOS/Windows podman already runs inside a `podman machine` VM, so a
non-libkrun runtime there shares only that VM's kernel, not the host's - the
run-time warning can soften/skip on those platforms. These warnings turn the
honest-help caveat above into an ACTIVE guardrail, which is what justifies the
`vm` suffix.

## CLAUDE.md amendment needed

The current namespace rule ("every face role owns exactly one hyphenated subdir;
utility roles must NOT own a top-level subdir - they guest inside a face role's
subdir") has no slot for a dir SHARED by multiple face roles. Add a third
category:

> **Shared prebuilt-asset dirs.** A top-level subdir owned by an internal
> `_`-prefixed producer role and consumed by several face roles (e.g.
> `shared-prebuilt-provision-assets/`, produced by
> `roles/_shared_prebuilt_provision_assets`). It is a REGENERABLE cache: any
> consumer's apply rebuilds it; it holds no unique state. Lifecycle: not removed
> by any single consumer's uninstall (others may still need it); a dedicated
> cleanup removes it. This is the only sanctioned exception to "utility roles
> don't own a top-level subdir".
