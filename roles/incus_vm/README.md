# roles/incus_vm

Installs **`ivm`** - a single Python launcher that creates and manages Incus KVM
VMs from declarative YAML templates. One VM per project directory; the guest gets
a full separate kernel (stronger isolation than a shared-kernel container).

> [!IMPORTANT]
> Host-level concerns (supported distros, what gets installed on the host, the
> storage pool config matrix, CoW backends, openSUSE+snapper trap, moving the
> install tree, NAT vs bridge, virt-manager coexistence) are in
> [`docs/incus-host-setup.md`](docs/incus-host-setup.md).
> Also: [`docs/incus-hardware-capabilities.md`](docs/incus-hardware-capabilities.md)
> (what `hw.*`/`net.*` incus can and can't do, GPU), and
> [`docs/incus-vs-podman.md`](docs/incus-vs-podman.md) (why VMs here, not incus containers).

## Quick start

```bash
make incus-install          # install `ivm` + example templates (+ host incus setup)
cd ~/projects/foo
ivm init claude              # build a VM from the `claude` template, bound to this dir
ivm shell                    # zsh into it (Claude Code is on PATH inside)
ivm snapshot create clean    # before risky changes
ivm stop                     # shut down (disk state preserved)
```

`ivm` reads no arguments for everyday commands - it resolves *which* VM by the
current directory (see [VM identity](#vm-identity)).

## Templates

A template describes a VM once, in YAML, at
`~/.local/share/ansible-managed/incus-vm/ivm/templates/<name>.yaml`, validated
against `ivm/template.schema.json` (the files carry a `# yaml-language-server:
$schema=...` modeline, so an editor with the YAML LSP shows inline field docs +
validation). Shipped examples: `claude`, `codex`, `webbrowser`, `windows11`.

Field groups (see the schema for the full, authoritative list):

| Block | Keys |
|---|---|
| `os` | `type` (`linux`/`windows`), `distro` (debian/ubuntu/opensuse/fedora; linux), `image.{source,uri}` |
| `hw` | `cpu`, `memory` (`8G`), `disk` (`30G`), `secureboot`, `tpm`, `nested_virt` (host-gated) |
| `sys` | `gui`, `timezone`, `tmpfs[]`, `ssh_server.{enabled,port,root_login,password_login,authorized_keys}` |
| `net` | `mode` (`nat`/`macvlan`/`bridge`), `parent` |
| `mounts[]` | `host`, `guest`, `ro`, `shadow[]` (subpaths to mask, e.g. `.git`) |
| (linux provisioning) | `distro_package_groups[]`, `distro_packages[]`, `dotfiles[]`, `post_install_script` |
| `windows` | `unattend`, `post_install_powershell` |

- `distro_package_groups` reference bundles in `roles/distro_packages`
  (`basic_tools`, `sys_tools`, ...); resolved per the VM's ansible_os_family. A
  fixed baseline (`incus_guest_baseline`: zsh + plugins, sudo, sshd, git, ...) is
  always installed.
- `mounts[].host` is shell-expanded on the HOST at init (`$(pwd)`, `$HOME`, `~`,
  relative paths).
- GPU acceleration is intentionally absent - incus can't do shared virtio-gpu 3D;
  see [`docs/incus-hardware-capabilities.md`](docs/incus-hardware-capabilities.md).

## Subcommands

`ivm <subcommand>`. Global flags: `--dry-run` (print the incus commands, run
nothing), `-y`/`--yes` (skip prompts), `--root <dir>` (override the data root),
`--name <vm>` (target that existing VM by name, ignoring the cwd binding; applies
to every VM-acting subcommand, not `init`/`env`/`list`).

| Subcommand | What it does |
|---|---|
| `init <template> [name]` | Create a VM from `<template>`, bound to the current dir. Prompts for the name (default `ivm-<template>-<cwd-path>`, editable) unless given; confirms before creating. |
| `list [incus args]` | `incus list` passthrough (e.g. `ivm list --format csv`). Shows all instances; ivm VMs are `ivm-`prefixed. |
| `info` | The target VM's live state: status, image, hw, network, mounts, + the storage pool its disk lives in (incl. the loop `.img` + usage). Target = cwd or `--name`. Read-only. |
| `shell` / `shell-user` | zsh into the target VM as `user` (starts it if stopped). |
| `shell-root` | zsh into it as `root`. |
| `start` / `stop` | Start / stop the target VM. |
| `reboot` | `incus restart` the target VM. |
| `delete` | Delete the VM + its disk + snapshots (asks first; `--yes` skips). |
| `update` | Refresh + upgrade all packages in the VM (per-family apt/zypper/dnf). |
| `overwrite-dotfiles` | Re-push the host-staged dotfiles into the VM (no re-provision). |
| `set-password <username>` | Set a guest account's login password (e.g. `user` for console/TTY login). Password only - prompted, sent via stdin. |
| `unset-password <username>` | Lock that account's password. |
| `enable-user-sudo` | Opt into in-guest sudo: `user` may sudo, gated by ROOT's password (`Defaults:user rootpw`). Needs `set-password root` first. |
| `disable-user-sudo` | Remove the sudoers drop-in (back to locked-down default). |
| `snapshot [create\|list\|restore\|delete] [name]` | Thin wrapper over `incus snapshot`, with the VM filled in. |
| `gui` | Open a SPICE graphical console (`incus console --type=vga`; needs `virt-viewer`/`remote-viewer` on the host + a desktop + `spice-vdagent` in the guest). |
| `env <template>` | Load + validate a template and print its resolved config (incl. the flattened package list). |

## VM identity

`init` tags the VM with `user.ivm_init_at_dir=<cwd>`. The cwd-resolved commands
(`shell`, `start`, `stop`, ...) find the VM whose tag matches the current dir.
Run one from a SUBDIR of an init'd project and `ivm` offers the nearest
ancestor's VM (`open '<vm>' init'd at <parent>? [Y/n]`). The instance name is
free-form (you edit it at init); resolution is by the tag, not the name.

## Provisioning model

`ivm` drives everything from the HOST via `incus exec` - the guest gets no
ansible/python. `init` does: `incus create` (stopped) -> attach devices (mounts +
`shadow` masks, `hw.tpm`, macvlan/bridge nic) -> `incus start` -> provision
(install baseline+groups+packages for the distro, set timezone + tmpfs, create
`user`, set both shells to zsh, configure sshd, run `post_install_script` as root
- it drops to `user` via `su - user -c '...'` for user-scoped bits) -> push the
staged user/root dotfiles. Linux on Debian / openSUSE / Fedora.

## Where files live

| What | Path |
|---|---|
| `ivm` binary | `~/.local/bin/ivm` |
| Schema | `~/.local/share/ansible-managed/incus-vm/ivm/template.schema.json` |
| Templates | `~/.local/share/ansible-managed/incus-vm/ivm/templates/*.yaml` |
| Package-group snapshot | `~/.local/share/ansible-managed/incus-vm/ivm/distro-package-groups.json` |
| Staged VM dotfiles | `~/.local/share/ansible-managed/incus-vm/ivm/rootfs/<family>/{home/user,root}/` |
| zsh / bash completion | `~/.local/share/ansible-managed/incus-vm/{zsh,bash}-completions/` |
| VM disk / snapshots (incus default pool) | `/var/lib/incus/storage-pools/default/virtual-machines[-snapshots]/<vm>/` |

`ivm --root` (env `IVM_ROOT`) points at the `incus-vm/ivm/` dir; the completion
dirs are siblings so the shell rc globs (`ansible-managed/*/{zsh,bash}-completions`)
discover them. Storage layout details: [`docs/incus-host-setup.md`](docs/incus-host-setup.md).

## Cleanup

| What | Command |
|---|---|
| Delete one VM (config + disk + snapshots) | `ivm delete` (from its dir), or `incus delete <vm>` |
| Re-push dotfiles to every managed guest | `make incus-push-dotfiles` |
| Remove `ivm` + the role's subdir (leaves VMs intact) | `make incus-uninstall-ivm` |
| List managed VMs | `incus list user.ansible-managed=true` |

## Status / limitations

- Statically verified (mypy `--strict`, `ivm --dry-run`, `make incus-sandbox`);
  real-incus end-to-end (launch / exec / virtio-fs) needs a real incus host.
- Windows tier (`os.type: windows`) is schema-defined but not yet implemented in
  `init` (linux only for now).
- No GPU acceleration (incus limitation; see hardware-capabilities doc).
