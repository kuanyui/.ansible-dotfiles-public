# incus_vm (`ivm` launcher) - implementation plan

Builds `ivm`, the launcher that replaces the bash launchers. Design = `REDESIGN.md`
(esp. §8) + the schema/examples in `files/` (`template.schema.json`, `templates/`).

## Architecture

- **`ivm`** = a static Python 3 program (type-annotated; stdlib + PyYAML +
  jsonschema). Reads VM templates + the schema from fixed install paths.
- **`roles/incus_vm`** (ansible) installs: the `ivm` binary into `~/.local/bin/`,
  `template.schema.json` + example templates into
  `~/.local/share/ansible-managed/incus-vm/ivm/`, the host deps (python3-yaml,
  python3-jsonschema via `_install_distro_packages`), two-level shell completion,
  and the staged user/root dotfiles (via `tasks/stage_dotfiles.yml`).
- Provisioning runs from the HOST via `incus exec`; the guest gets no
  ansible/python (REDESIGN §8.1).

## Subcommand surface

- `ivm init <template>` - the only one taking a template id; interactive name
  prompt + dir-binding (REDESIGN §8.9).
- `ivm <shell|shell-root|start|stop|delete|env|overwrite-dotfiles|update|set-password|unset-password|enable-user-sudo|disable-user-sudo|snapshot|gui>` -
  resolve the VM by cwd via `user.ivm_init_at_dir`; no VM-name arg
  (`set-password`/`unset-password` take a guest `<username>`).
- Global: `--dry-run` (print the incus commands, run nothing), `--yes`.

## Reuse (do not reinvent)

`tasks/incus_host_install.yml` (host prep) + `tasks/stage_dotfiles.yml` (user+root
dotfile staging), both folded in from the former `_incus_*` roles;
`roles/distro_packages` (the `distro_package_groups` registry); `roles/thirdparty_software`
(the `thirdparty_software` install-recipe registry, materialized to
`thirdparty-software.json` for `ivm`).

## Phases (each testable on a real incus host)

| Phase | Content |
| --- | --- |
| **0 scaffold** | role installs `ivm` + schema + deps + example templates; `ivm --help`, `ivm env <template>` (load + schema-validate + print resolved config), `--dry-run` plumbing. |
| **1 minimal Linux happy path (Debian)** | `ivm init <template>`: validate -> name prompt (default `<template>-<cwd-path>`, editable, length+uniqueness loop) -> `incus launch` + `user.*` tags -> attach mounts -> minimal provision (pkg install + push dotfiles) ; `ivm shell` (cwd-resolve -> `incus exec` zsh). Goal: `ivm init claude` then `ivm shell`. |
| **2 lifecycle + provision depth** | start/stop/delete (with delete confirm), overwrite-dotfiles, update, env; `post_install_script` (root, `su - user` for user bits), baseline pkgs, `distro_package_groups` resolution; add openSUSE/Fedora (distro -> pkg-mgr + os_family map). |
| **3 extras** | shadow mounts, `sys.tmpfs`, `ssh_server`, `hw.gpu` virtio, `net` macvlan/bridge, snapshot CLI, gui (SPICE), parent-dir prompt, two-level completion. |
| **4 retire** | migrate claude/codex to `ivm`; retire `roles/incus_agents` + the old bash launchers. Once `incus_agents` is gone, `incus_vm` is the sole consumer of the `_incus_*` roles. DONE: folded BOTH `_incus_*` roles into `incus_vm` (no second incus consumer exists - ivm is a general launcher, new use cases are templates not roles; incus containers aren't worth it vs podman, see docs/incus-vs-podman.md). `_incus_guest_setup_dotfiles` -> `tasks/{stage_dotfiles,_stage_family}.yml` (vars renamed `incus_vm_dotfiles_*`). `_incus_host_setup` -> `tasks/incus_host_install.yml` (later renamed from `host_setup.yml` when its `incus_host_uninstall.yml` counterpart was added) + its storage-pool vars -> `defaults/main/incus_host_install.yml` (with the install vars in `defaults/main/ivm_install.yml`) + `incus_preseed.yml.j2` -> `templates/` + its README -> `docs/incus-host-setup.md`. Both roles deleted. `make incus-push-dotfiles` kept (filters by `user.ansible-managed`); `ivm overwrite-dotfiles` is the per-VM alternative. **Layout reorg DONE:** all `ivm` data nested under `incus-vm/ivm/` with the now-redundant prefixes dropped - `template.schema.json`, `templates/`, `rootfs/<family>/`, `distro-package-groups.json`; `ivm --root` (`DEFAULT_ROOT`) = `incus-vm/ivm` (ansible var `incus_vm_ivm_dir`); `{zsh,bash}-completions/` kept as SIBLINGS at `incus-vm/` (matched by the rc globs), so program data and completions are cleanly separated. |

Windows = separate future tier (REDESIGN §8 / §4.8); not in this plan.

## Validation (three layers)

| Layer | Tool |
| --- | --- |
| role's ansible install path (install.yml: deps, ivm/schema/templates placement, completion, dotfiles staging) | `make incus-sandbox` (throwaway podman+systemd; incus stubbed) |
| `ivm` logic (arg parse, name gen/validate, the incus commands it builds) | `ivm --dry-run` + python checks |
| end-to-end (real `incus launch`/exec/push) | a real incus host |

NOTE: `scripts/sandbox/configs/incus_vm.py` currently exercises the OLD bash
launcher install; it must be updated alongside the new `install.yml` (phase 0/1).

## Open (deferred)

- User-authored templates in an uninstall-safe location (`ivm` just scans
  one more dir later; not needed for v1).
