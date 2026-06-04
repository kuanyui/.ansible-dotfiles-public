# incus_vm engine - implementation plan

Builds the `ivm` engine that replaces the bash launchers. Design = `REDESIGN.md`
(esp. §8) + the schema/examples in `files/` (`vm.schema.json`, `vm-templates/`).

## Architecture

- **`ivm`** = a static Python 3 program (type-annotated; stdlib + PyYAML +
  jsonschema). Reads VM templates + the schema from fixed install paths.
- **`roles/incus_vm`** (ansible) installs: the `ivm` binary into `~/.local/bin/`,
  `vm.schema.json` + example templates into
  `~/.local/share/ansible-managed/incus-vm/`, the host deps (python3-yaml,
  python3-jsonschema via `_install_distro_packages`), two-level shell completion,
  and the staged user/root dotfiles (via `tasks/stage_dotfiles.yml`).
- Provisioning runs from the HOST via `incus exec`; the guest gets no
  ansible/python (REDESIGN §8.1).

## Subcommand surface

- `ivm init <template>` - the only one taking a template id; interactive name
  prompt + dir-binding (REDESIGN §8.9).
- `ivm <shell|shell-root|start|stop|delete|env|overwrite-dotfiles|update|set-root-password|unset-root-password|snapshot|gui>` -
  resolve the VM by cwd via `user.ivm_init_at_dir`; no name arg.
- Global: `--dry-run` (print the incus commands, run nothing), `--yes`.

## Reuse (do not reinvent)

`_incus_host_setup` (host prep, kept as a `_` role), `tasks/stage_dotfiles.yml`
(user+root dotfile staging, folded in), `roles/distro_packages` (the
`distro_package_groups` registry).

## Phases (each testable on a real incus host)

| Phase | Content |
| --- | --- |
| **0 scaffold** | role installs `ivm` + schema + deps + example templates; `ivm --help`, `ivm env <template>` (load + schema-validate + print resolved config), `--dry-run` plumbing. |
| **1 minimal Linux happy path (Debian)** | `ivm init <template>`: validate -> name prompt (default `<template>-<cwd-path>`, editable, length+uniqueness loop) -> `incus launch` + `user.*` tags -> attach mounts -> minimal provision (pkg install + push dotfiles) ; `ivm shell` (cwd-resolve -> `incus exec` zsh). Goal: `ivm init claude` then `ivm shell`. |
| **2 lifecycle + provision depth** | start/stop/delete (with delete confirm), overwrite-dotfiles, update, env; `post_install_script` (root, `su - user` for user bits), baseline pkgs, `distro_package_groups` resolution; add openSUSE/Fedora (distro -> pkg-mgr + os_family map). |
| **3 extras** | shadow mounts, `sys.tmpfs`, `ssh_server`, `hw.gpu` virtio, `net` macvlan/bridge, snapshot CLI, gui (SPICE), parent-dir prompt, two-level completion. |
| **4 retire** | migrate claude/codex to `ivm`; retire `roles/incus_agents` + the old bash launchers. Once `incus_agents` is gone, `incus_vm` is the sole consumer of the `_incus_*` roles. DONE: folded `_incus_guest_setup_dotfiles` -> `roles/incus_vm/tasks/{stage_dotfiles,_stage_family}.yml` (small, tightly coupled; vars renamed `incus_vm_dotfiles_*`). KEPT `_incus_host_setup` as a `_` role (large + self-contained host-daemon prep with its own defaults/template; the `_` convention allows single-consumer internal helpers, and a future incus face role could reuse it - folding would only bloat incus_vm). `make incus-overwrite-dotfiles-in-all-guest` kept (filters by `user.ansible-managed`); `ivm overwrite-dotfiles` is the per-VM alternative. (Skip the fold-in only if a NEW incus face role is planned that genuinely re-shares them.) **Layout reorg (do it here, as one move - it needs the staging role to be ivm-only first):** nest all `ivm` data under `incus-vm/ivm/` and drop the now-redundant prefixes - `vm.schema.json` -> `ivm/template.schema.json`, `vm-templates/` -> `ivm/templates/`, `vm-rootfs/<family>/` -> `ivm/rootfs/<family>/`, `package-groups.json` -> `ivm/package-groups.json`; point `ivm --root` (`DEFAULT_ROOT`) at `incus-vm/ivm`; keep `zsh-completions/` as a SIBLING at `incus-vm/zsh-completions/` (the `ansible-managed/*/zsh-completions` glob matches it there). This cleanly separates completions from program data. Until then the interim names (`vm.schema.json`, `vm-templates/`, `vm-rootfs/`) stay at the `incus-vm/` root. |

Windows = separate future tier (REDESIGN §8 / §4.8); not in this plan.

## Validation (three layers)

| Layer | Tool |
| --- | --- |
| role's ansible install path (install.yml: deps, ivm/schema/templates placement, completion, dotfiles staging) | `make sandbox-incus-vm` (throwaway podman+systemd; incus stubbed) |
| engine logic (arg parse, name gen/validate, the incus commands it builds) | `ivm --dry-run` + python checks |
| end-to-end (real `incus launch`/exec/push) | a real incus host |

NOTE: `scripts/sandbox/configs/incus_vm.py` currently exercises the OLD bash
launcher install; it must be updated alongside the new `install.yml` (phase 0/1).

## Open (deferred)

- User-authored templates in an uninstall-safe location (the engine just scans
  one more dir later; not needed for v1).
