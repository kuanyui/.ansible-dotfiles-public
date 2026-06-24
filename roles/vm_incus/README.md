# roles/vm_incus

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
> [`docs/incus-vs-podman.md`](docs/incus-vs-podman.md) (why VMs here, not incus containers),
> and [`docs/ivm-vs-quickemu.md`](docs/ivm-vs-quickemu.md) (how `ivm` compares to quickemu).

## Quick start

```bash
make vm-incus-install          # install `ivm` + example templates (+ host incus setup)
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
`~/.local/share/ansible-managed/vm-incus/ivm/templates/<name>.yaml`, validated
against `ivm/template.schema.json` (the files carry a `# yaml-language-server:
$schema=...` modeline, so an editor with the YAML LSP shows inline field docs +
validation). Shipped examples: `base_debian` / `base_opensuse` / `base_fedora`
(bare distro + `tools_basic`, nothing else), `claude`, `codex`, `webbrowser`,
`windows11`.

Field groups (see the schema for the full, authoritative list):

| Block | Keys |
|---|---|
| `os` | `type` (`linux`/`windows`), `distro` (debian/ubuntu/opensuse/fedora; linux), `image.{source,uri}` |
| `hw` | `cpu`, `memory` (`8G`), `disk` (`30G`), `secureboot`, `tpm`, `nested_virt` (host-gated) |
| `sys` | `gui`, `timezone`, `tmpfs[]`, `ssh_server.{enabled,port,root_login,password_login,authorized_keys}` |
| `net` | `mode` (`nat`/`macvlan`/`bridge`), `parent` |
| `mounts[]` | `host`, `guest`, `ro`, `shadow[]` (subpaths to mask, e.g. `.git`) |
| (linux provisioning) | `distro_package_groups[]`, `distro_packages[]`, `thirdparty_software[]`, `dotfiles[]`, `post_install_script` |
| `windows` | `unattend`, `post_install_powershell` |

- `distro_package_groups` reference bundles in `roles/provision_distro_packages`
  (`tools_basic`, `tools_sys`, ...); resolved per the VM's ansible_os_family. A
  fixed baseline (`incus_guest_baseline`: zsh + plugins, sudo, sshd, git, ...) is
  always installed.
- `thirdparty_software` reference non-distro install recipes in
  `roles/provision_thirdparty_software` (`claude`, `codex`, ...): a shell snippet run as root
  in the guest (3rd-party repo / `curl|bash` / npm-pip) with an optional
  idempotency probe - for software not in the distro repos.
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
| `info` | The target VM's live state: status, image, hw, network, **forwards** (`expose`d ports), mounts, + the storage pool its disk lives in (incl. the loop `.img` + usage). Target = cwd or `--name`. Read-only. |
| `shell` / `shell-user` (aliases `sh` / `sh-user`) | zsh into the target VM as `user` (starts it if stopped). Starts in the template's `shell_default_dir_after_login` when set + present in the guest (else the home dir); only the start dir, `$HOME` / `cd` unaffected. |
| `shell-root` (alias `sh-root`) | zsh into it as `root`. |
| `start` / `stop` | Start / stop the target VM. |
| `reboot` | `incus restart` the target VM. |
| `delete` | Delete the VM + its disk + snapshots (asks first; `--yes` skips). |
| `update` | Refresh + upgrade all packages in the VM (per-family apt/zypper/dnf). |
| `resize [--cpu N] [--memory NG] [--disk NG]` | Change an existing VM's vCPU / RAM / root-disk (the template `hw.*` only applies at `init`). cpu/memory apply live; **disk grows only** (refuses shrink) and resizes just the host block device - the guest fs needs `ivm reboot` or in-guest `growpart`+`resize2fs`. |
| `mount ls\|attach\|shadow\|detach` | Inspect / change a VM's virtio-fs shares after creation (template `mounts` only apply at `init`, but incus disk devices hotplug for VMs). `attach <host> <guest> [--ro] [--shadow SUB ...]` (`--shadow` masks subpaths *of this mount*, at attach time); `shadow <guest_path>` masks one **already-existing guest directory** with an empty read-only dir, independent of any mount (e.g. hide a mounted project's `.git` you forgot to `--shadow`). Directories only - a VM disk device can't mask a single file. `detach <mount>` (drops its masks too) **or** `detach <masked-path>` to un-mask one subpath. `detach` only unbinds the share - **host data is never deleted**. `ls`. |
| `push <local> <guest> [--as-root]` | Copy a host file/dir into the VM (`incus file push`, one-shot snapshot). Owns files as `user` (uid/gid 1000) by default; `--as-root` for root. A directory goes recursively; the guest path must be absolute; the VM is started if stopped. For a live two-way share, use `mount attach` instead. |
| `expose [<port>\|<host>:<guest>]` | Open a host TCP port to the VM so the **LAN** can reach a service inside it - the simple alternative to building a host bridge. **Needs proxy devices allowed in the user project** - `vm-incus-install` does this by default (`vm_incus_allow_proxy_devices: true`; set false on a shared/multi-user host); on a host set up before this feature, re-run it, or run `sudo incus project set user-$(id -u) restricted.devices.proxy=allow` once. Then: host<->VM already works over incusbr0 NAT; this only ADDS the LAN path via an incus **proxy device** (`nat=true`): the LAN hits `<this-host-ip>:<port>` and incus forwards it in. `<port>` = same port both ends, or `<host-port>:<guest-port>` (docker `-p` style). Pins the VM's IPv4 first (the proxy needs a static target; pinned to the current lease, so no reboot). No arg lists the current forwards. Opens only that one port - for "VM as a full LAN host" you still need a bridge (see [incus-host-setup.md](docs/incus-host-setup.md)). |
| `unexpose [<host-port>]` | Remove a forward added by `expose`. No arg removes **all** of this VM's forwards (confirms; `--yes` skips). |
| `overwrite-dotfiles` | Re-push the host-staged dotfiles into the VM (no re-provision). |
| `set` / `unset` (no aspect) | List the configurable guest-setting aspects (password / ssh-server / shell-dir / user-sudo) with one-line descriptions. Every aspect has both `set` and `unset`. |
| `set password <username>` / `unset password <username>` | Set (prompted, sent via stdin) / lock a guest account's login password (e.g. `user` for console/TTY login). Password only. |
| `set ssh-server <username> [--pubkey FILE]` / `unset ssh-server <username> [--pubkey FILE]` | Authorize / revoke key-based SSH login for a guest account (`user`/`root`) - e.g. for VS Code Remote-SSH. `set` appends `--pubkey` (repeatable; default `~/.ssh/id_ed25519.pub`) to that account's `authorized_keys` (idempotent - keeps keys you added by hand) and ensures sshd is up; `root` also gets `PermitRootLogin prohibit-password`. `unset` removes the key(s) (and root's override); leaves sshd running. Key-only, no password auth. Port/password tuning lives in the template's `sys.ssh_server`. |
| `set shell-dir <path>` / `unset shell-dir` | Set / clear the directory `ivm sh` starts in (the `user.ivm_shell_default_dir_after_login` tag; also set at `init` from a template's `shell_default_dir_after_login`). Only the interactive shell's start cwd - `$HOME` and a bare `cd` are unchanged. `<path>` is an absolute GUEST path; it need not exist yet (`ivm sh` warns + falls back to the default cwd if missing). `unset` reverts to incus's default cwd. |
| `set user-sudo` / `unset user-sudo` | Opt `user` in / out of in-guest sudo: `user` may sudo, gated by ROOT's password (`Defaults:user rootpw`). Needs `set password root` first. `unset` removes the sudoers drop-in (back to the locked-down default). |
| `snapshot [create\|list\|restore\|delete] [name]` | Thin wrapper over `incus snapshot`, with the VM filled in. |
| `gui` | Open the VM's SPICE graphical console (`incus console --type=vga`), **detached** from the shell so you can close the terminal without killing it. Needs `remote-viewer` (virt-viewer) or `spicy` (spice-gtk) on the host + a desktop + `spice-vdagent` in the guest. |
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
| Schema | `~/.local/share/ansible-managed/vm-incus/ivm/template.schema.json` |
| Templates | `~/.local/share/ansible-managed/vm-incus/ivm/templates/*.yaml` |
| Provision-asset cache (SHARED w/ qvm/pvm) | `~/.local/share/ansible-managed/shared-prebuilt-provision-assets/{distro-package-groups,thirdparty-software}.json` |
| Staged VM dotfiles (feature-first, in the shared cache) | `.../shared-prebuilt-provision-assets/dotfiles/<feature>/{__common__,<family>}/{home/user,root}/` |
| zsh / bash completion | `~/.local/share/ansible-managed/vm-incus/{zsh,bash}-completions/` |
| VM disk / snapshots (incus default pool) | `/var/lib/incus/storage-pools/default/virtual-machines[-snapshots]/<vm>/` |

`ivm --root` (env `IVM_ROOT`) points at the `vm-incus/ivm/` dir (ivm-only assets:
schema, templates, fcitx5 script, storage-info). The package-group/thirdparty JSON +
the dotfiles tree live in the SHARED `shared-prebuilt-provision-assets/` cache
(`ivm --shared-assets-root`, env `SHARED_PREBUILT_PROVISION_ASSETS_ROOT`; default is
standard, rarely set) because qvm/pvm consume them too. The completion dirs are
siblings so the shell rc globs (`ansible-managed/*/{zsh,bash}-completions`) discover
them. Storage layout details: [`docs/incus-host-setup.md`](docs/incus-host-setup.md).

## Cleanup

| What | Command |
|---|---|
| Delete one VM (config + disk + snapshots) | `ivm delete` (from its dir), or `incus delete <vm>` |
| Re-push dotfiles to every managed guest | `make vm-incus-push-dotfiles` |
| Remove `ivm` + the role's subdir (leaves VMs intact) | `make vm-incus-uninstall-ivm` |
| List managed VMs | `incus list user.ansible-managed=true` |

## Status / limitations

- Statically verified (mypy `--strict`, `ivm --dry-run`, `make vm-incus-sandbox`);
  real-incus end-to-end (launch / exec / virtio-fs) needs a real incus host.
- Windows tier (`os.type: windows`) is schema-defined but not yet implemented in
  `init` (linux only for now).
- No GPU acceleration (incus limitation; see hardware-capabilities doc).
