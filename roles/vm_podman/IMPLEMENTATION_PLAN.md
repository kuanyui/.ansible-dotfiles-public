# vm_podman / `pvm` implementation plan (REFACTOR.md Phase 3)

Durable, in-repo copy of the approved Phase 3 plan (cross-machine; the plan-mode
scratch file under `~/.claude/` is local-only and not authoritative).

## Context

REFACTOR.md Phase 3 is the last unticked phase. The podman feature was the same
shape `ivm` replaced on the incus side: per-`(template,runtime)` bash launchers
`~/.local/bin/c-<tpl>-<rt>` (`roles/container_apps`) `exec`ing a 454-line
Jinja-in-bash `host-cli.sh.j2` (`roles/container_templates`), with duplicated
`zshrc.j2`/`bashrc.j2`. Goal: fold both roles into ONE face role `roles/vm_podman`
shipping a Python launcher `pvm`, mirroring `vm_quickemu`/`qvm`, consuming the
shared provision-asset cache (Phases 1-2) so all engines share one source of truth.

## Decisions (settled with the user)

- **No Dockerfile.** `podman build` is the only thing that needs one; reusable
  images can be made CLI-only via `podman commit` (verified: docs.podman.io
  podman-commit; buildah.io). So `pvm` provisions a running container via
  `podman exec` + `podman cp` (like qvm's QGA / ivm's `incus file push`), then
  `podman commit`s a per-template image keyed by a **content-hash tag** for reuse.
  Deletes the hardest part of the old design (Dockerfile render + build-context
  assembly) and makes `pvm` a near-twin of `qvm`.
- **Runtime: default `crun`**, with shared-kernel guardrails (warn + a non-libkrun
  `init` `[y/N]` gate, default No, `--yes` bypass, non-TTY aborts). User-facing
  flag value `libkrun` maps to podman's `krun` handler.
- **libkrun: DEFERRED out of v1** (discouraged path + user is off podman). The
  shared-kernel warning points to **`ivm` (a real VM)**, not "prefer libkrun" - a
  deliberate, noted deviation from REFACTOR.md's wording. libkrun recipe recorded
  below for a later sub-phase.
- **Old-install migration: hard cut.** The user removes the old `c-*` launchers +
  `~/.local/share/ansible-managed/container-apps/` manually. No `prune-legacy`.

## Locked names (REFACTOR.md:44,46,80-84)

`pvm` binary; role `roles/vm_podman`; managed subdir `~/.local/share/ansible-managed/vm-podman/`,
pvm data in `vm-podman/pvm/`; env `PVM_HOME`; state var `vm_podman_state`;
`playbooks/vm_podman{,_uninstall}.yml`; Makefile `vm-podman-{install,check,uninstall-pvm,sandbox}`;
`scripts/sandbox/configs/vm_podman.py`; completions `_pvm` + `pvm.bash`.

## Core mechanism (crun, no Dockerfile)

```
pvm init <template>            # default --runtime crun
  family  = distro_family_of_image(tpl.image_name)         # Debian/Suse/RedHat
  resolved= <qvm resolver>(tpl groups+pkgs+thirdparty, family)
  hash    = sha256(tpl + resolved + dotfiles-slice + overlay)[:12]
  image   = pvm/<template>:<hash>
  if image missing (or --rebuild):                          # content-hash cache
    podman run --runtime crun -d --name <build> <tpl.image_name> sleep infinity
    podman exec  <build>  bash -c "<install_packages_script + thirdparty_install_script + post_install>"
    podman cp    <staged dotfiles {home/user,root} + overlay>  <build>:...   ; chown
    podman commit --change 'WORKDIR /workspaces' <build> <image> ; podman rm -f <build>
  # per-PROJECT container from the per-TEMPLATE image (mounts the cwd at run time):
  podman run --runtime crun -d --name pvm-<tpl>-<proj> --userns=keep-id \
    --volume <cwd>:/workspaces/<proj> [hide-dir empty-mounts] [--publish ...] --workdir <wd> <image>
pvm shell   -> podman exec -it --user user pvm-<tpl>-<proj> zsh
```

Per-template image (packages+dotfiles+agent are template-level, reused across
projects); per-project container (mounts cwd). Dotfiles + provision come from the
SHARED cache, delivered by `podman cp`/`exec` instead of `incus file push`.

## Templates mirror ivm/qvm, NOT the old schema

pvm templates use the shared-cache feature keys (like
`roles/vm_incus/files/templates/claude.yaml`): `distro_package_groups[]`,
`distro_packages[]`, `thirdparty_software[]` (the agent install IS a thirdparty
recipe - `claude`/`codex` already in the render dict
`_shared_prebuilt_provision_assets/tasks/main.yml`), `dotfiles[]`, plus container
bits: `image_name`, `image_platform`, `tz`, `runtimes[]`, `publish_ports[]`,
`mounts[]` (+ `shadow`). Old `feature_presets`/`install_script_url`/`nodejs` map
onto shared-cache features; add a new render-dict key ONLY if a needed feature is
absent (CLAUDE.md registry->render-dict sync rule), noted in the commit.

## Sub-phases (each: finish -> verify -> commit)

### 3.0 Scaffold  [this commit]
Role mirroring `roles/vm_quickemu`: `files/pvm` skeleton (env/list/help wired;
every other subcommand registered but errors with the sub-phase that adds it),
`files/test_pvm.py`, `files/completions/{_pvm,pvm.bash}`, `defaults/main.yml`,
`tasks/{main,pvm_install,pvm_uninstall,podman_host_install}.yml` (pvm_uninstall =
**3-way** ref-count: stat ivm AND qvm), README, `playbooks/vm_podman{,_uninstall}.yml`,
`scripts/sandbox/configs/vm_podman.py`, Makefile `vm-podman-*`. ivm/qvm uninstall
upgraded to the 3-way ref-count too (pvm is now a third cache consumer). Repo
hygiene (the dead `roles/incus_vm` cruft + committed `.pyc`) was a no-op: nothing
is git-tracked there (`.gitignore` already covers `__pycache__/` + `*.pyc`).

### 3.1 Declarative templates + schema + ported pure logic (no podman calls)
`files/template.schema.json` (mirror ivm), `files/templates/{claude,codex}.yaml`.
Port `container_templates/filter_plugins/distro.py` -> `distro_family_of_image()`;
port `host-cli.sh.j2` naming/mount/project-name/run-argv to pure typed Python +
unit tests. `pvm run --dry-run` prints the correct `podman run` argv, no podman.

### 3.2 Consume shared cache: provision-via-exec + `podman commit` (crun)
Copy the qvm resolver block verbatim; `content_hash()`; `build_image_if_missing()`
(run base -> exec provision -> `podman cp` dotfiles slice + `overlay/` -> commit).
`files/overlay/workspace-autocd.{zsh,bash}` (the only container-specific dotfile
bit, from `container_templates/templates/zshrc.j2`). Wire dynamic completions to
the shared JSON. 3-way ref-count goes live.

### 3.3 Real podman drive + lifecycle + guardrails (crun; first privileged sub-phase)
Implement init/run/start/stop/rmc/rmi/rma/shell/agent against real podman.
Guardrails: `warn_shared_kernel()` -> points to `ivm` (install + per-run);
`gate_non_libkrun_init()` -> `[y/N]` default No, `--yes` bypass, non-TTY aborts;
macOS/Windows softened. Host-only verify.

### 3.4 Retire `container_apps` + `container_templates`
`git rm` both roles + their playbooks + container_apps sandbox config; Makefile
cleanup; tick REFACTOR.md Phase 3 (note libkrun deferred); README migration note.
grep old names == 0; syntax-check; `make help`.

## Deferred (NOT v1): libkrun (a later 3.5)

`podman run --runtime krun`; `podman exec` cannot enter the microVM (crun
#1098/#2090) and systemd cannot run (libkrun pins `init.krun` as PID 1;
`container_templates/templates/Dockerfile.j2`). sshd is the entry. Adapt the commit
pipeline: under **crun** (exec works) also install `openssh-server` + `ssh-keygen -A`
+ `mkdir /run/sshd` + write user/root `authorized_keys` from a host key (ed25519)
+ `PermitRootLogin prohibit-password`, then
`podman commit --change 'CMD ["/usr/sbin/sshd","-D","-e"]'`. Run:
`podman run --runtime krun --annotation krun.cpus=<n> --annotation krun.ram_mib=<mib> --publish 127.0.0.1::22 <image>`;
enter via `ssh -p $(podman port <ctr> 22) -i <PVM_HOME>/host_ssh_key`. (Sources:
crun `krun.1.md` annotations; podman-commit docs.)
