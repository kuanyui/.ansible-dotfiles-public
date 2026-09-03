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

> [!NOTE]
> Normative behavior + architecture: [`SPEC.md`](SPEC.md) (the contract - what
> every subcommand must do, the invariants, host prerequisites) and
> [`DESIGN.md`](DESIGN.md) (how/why `ivm` is built). The redesign decision log
> that produced `ivm` is archived at [`docs/redesign-history.md`](docs/redesign-history.md).

## Quick start

```bash
make vm-incus-install          # install `ivm` + example templates (+ host incus setup)
cd ~/projects/foo
ivm init agent_claude        # build a VM from the `agent_claude` template, bound to this dir
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
(bare distro + `tools_basic`, nothing else), `llm_sillytavern` / `llm_openwebui` /
`llm_librechat` (self-contained LLM chat appliances, each with an in-guest
`llm-backup` helper that tars app data into the host-shared `~/Downloads`),
`agent_claude`, `agent_codex`, `webbrowser`, `windows11`.

Field groups (see the schema for the full, authoritative list):

| Block | Keys |
|---|---|
| `os` | `type` (`linux`/`windows`), `distro` (debian/ubuntu/opensuse/fedora; linux), `image.{source,uri}` |
| `hw` | `cpu`, `memory` (`8G`), `disk` (`30G`), `secureboot`, `tpm`, `nested_virt` (host-gated) |
| `sys` | `gui`, `timezone`, `tmpfs[]`, `ssh_server.{enabled,port,root_login,password_login,authorized_keys}` |
| `net` | `mode` (`nat`/`macvlan`/`bridge`), `parent` |
| `mounts[]` | `host`, `guest`, `ro`, `shadow[]` (subpaths to mask, e.g. `.git`) |
| `host_bound_dir` | REQUIRED. Host dir the VM binds to for cwd resolution, host-expanded (`$(pwd)` = the init dir - project boxes); `""` = unbound appliance, target it by name (the `llm_*` templates). |
| `services` | Host-reachable endpoints as `name: port` (e.g. `webui: 8080`) - an annotation `ivm info` prints as `name=<ip>:<port>` (via the `user.ivm_services` tag); `init` warns if a declared port's literal is missing from `post_install_script`. |
| (linux provisioning) | `distro_package_groups[]`, `distro_packages[]`, `thirdparty_software[]`, `post_install_script` |
| `windows` | `unattend`, `post_install_powershell` |

- `distro_package_groups` reference bundles in
  `roles/provision/defaults/main/distro_packages.yml`
  (`tools_basic`, `tools_sys`, ...); resolved per the VM's ansible_os_family. A
  fixed baseline (`incus_guest_baseline`: zsh + plugins, sudo, sshd, git, ...) is
  always installed.
- `thirdparty_software` reference non-distro install recipes in
  `roles/provision/defaults/main/thirdparty_software.yml` (`agent_claude`, `agent_codex`, ...): a shell snippet run as root
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

**Targeting a VM by name.** Commands that take no argument of their own - `shell*`,
`start`/`stop`/`reboot`/`delete`, `update`, `overwrite-dotfiles`, `gui`, `info`,
`resize` - also accept a trailing VM name: `ivm stop foo`, `ivm info foo`, `ivm sh
foo` (a shortcut for `--name`, tab-completed with each VM's bound dir shown in
zsh). Omit it to resolve by the current directory. Commands that DO take an argument
(`provision`, `push`, `mount`, `snapshot`, `expose`, `unexpose`) use `--name` only.
`rename` is the exception: its target is an optional **leading** positional -
`ivm rename <old> <new>` (the `incus rename` order), or `ivm rename <new>` resolved
by cwd / `--name`.

| Subcommand | What it does |
|---|---|
| `init <template> [name]` | Create a VM from `<template>`, bound per the template's required `host_bound_dir` (`$(pwd)` = the current dir; `""` = unbound - see [VM identity](#vm-identity)). Prompts for the name (default `ivm-<template>-<bound-dir-path>`, editable) unless given; confirms before creating. |
| `list [incus args]` | No arg: a table of ivm-**managed** VMs (State, Name, MEM(guest), MEM(host), Disk, Created, Up/Last-On, Working Directory, IPv4). `Created` is the incus `created_at` date + age; `Up/Last-On` shows a running VM's uptime since this boot, or a stopped VM's last **start** (`last on 19d ago` - incus never records a stop time; `(never started)` when it never ran). `MEM(guest)` is incus's guest-agent memory figure; `MEM(host)` is the qemu process's real host RSS, which the guest figure under-reports (no balloon reclaim - see `top`); `Disk` is the guest root filesystem's used space, read live per running VM via `incus exec … df` (reliable, unlike incus's sporadic VM disk metric - lxc/incus#259; it is guest-fs used, which can trail the host `root.img` footprint until `fstrim`). Non-running VMs show `(<state>)`. Any arg: raw `incus list` passthrough of **all** instances (e.g. `ivm list --format csv`). |
| `cd [<vm>]` | `cd` the shell into a VM's **host-bound dir** (`user.ivm_host_bound_dir`). Refuses an unbound/legacy VM. Tab-completes VM names, showing each VM's dir on the right (zsh). No arg lists the managed VMs + their dirs. Needs the `ivm()` shell wrapper (auto-installed; a child process can't change the parent shell's cwd). |
| `info` | The target VM's live state, **grouped** for readability: **Basic** (status/created/last-started/image/hw/snapshots/host-bound-dir/guest-shell-dir/user-sudo), **Network** (the VM's current **IP**, **services** = the template's declared endpoints as ready-to-open `name=<ip>:<port>`, bridge, ssh-server, **forwards** = `expose`d ports), **Mounts**, **Storage** (the pool its disk lives in, incl. the loop `.img` + usage). Target = cwd or `--name`. Read-only; prints every field with a placeholder when empty. |
| `shell` / `shell-user` (aliases `sh` / `sh-user`) | zsh into the target VM as `user` (starts it if stopped). Starts in the template's `shell_default_dir_after_login` when set + present in the guest (else the home dir); only the start dir, `$HOME` / `cd` unaffected. |
| `shell-root` (alias `sh-root`) | zsh into it as `root`. |
| `start` / `stop [--force]` | Start / stop the target VM. `stop` asks first (`--yes` skips). `--force` = `incus stop --force`: no clean guest shutdown, incus SIGKILLs the VM's qemu process. |
| `reboot [--force]` | `incus restart` the target VM (asks first; `--yes` skips). `--force` = `incus restart --force`: SIGKILL, then start. |
| `delete` | Delete the VM + its disk + snapshots (asks first; `--yes` skips). |
| `rename [<old-vm>] <new-name>` | Rename the VM (`incus rename`; stopped VMs only - `ivm stop` first; asks first, `--yes` skips). Snapshots and the dir binding travel with it, so cwd resolution keeps working. The LAST positional is the NEW name; give the old VM as the leading positional (`incus rename` order), or omit it to target by cwd / `--name`. |
| `update` | Refresh + upgrade all packages in the VM (per-family apt/zypper/dnf). |
| `resize [--cpu N] [--memory NG] [--disk NG]` | Change an existing VM's vCPU / RAM / root-disk (the template `hw.*` only applies at `init`). cpu/memory apply live; **disk grows only** (refuses shrink) and resizes just the host block device - the guest fs needs `ivm reboot` or in-guest `growpart`+`resize2fs`. |
| `mount ls\|attach\|shadow\|detach` | Inspect / change a VM's virtio-fs shares after creation (template `mounts` only apply at `init`, but incus disk devices hotplug for VMs). `attach <host> <guest> [--ro] [--shadow SUB ...]` (`--shadow` masks subpaths *of this mount*, at attach time); `shadow <guest_path>` masks one **already-existing guest directory** with an empty read-only dir, independent of any mount (e.g. hide a mounted project's `.git` you forgot to `--shadow`). Directories only - a VM disk device can't mask a single file. `detach <mount>` (drops its masks too) **or** `detach <masked-path>` to un-mask one subpath. `detach` prints what it will unbind (`device: host-source -> guest-path`) + confirms first (`--yes` skips); it only unbinds the share - **host data is never deleted**. `ls`. |
| `push <local> <guest> [--as-root]` | Copy a host file/dir into the VM (`incus file push`, one-shot snapshot). Owns files as `user` (uid/gid 1000) by default; `--as-root` for root. A directory goes recursively; the guest path must be absolute; the VM is started if stopped. For a live two-way share, use `mount attach` instead. |
| `expose [<port>\|<host>:<guest>]` | Open a host TCP port to the VM so the **LAN** can reach a service inside it - the simple alternative to building a host bridge. **Needs proxy devices allowed in the user project** - `vm-incus-install` does this by default (`vm_incus_allow_proxy_devices: true`; set false on a shared/multi-user host); on a host set up before this feature, re-run it, or run `sudo incus project set user-$(id -u) restricted.devices.proxy=allow` once. Then: host<->VM already works over incusbr0 NAT; this only ADDS the LAN path via an incus **proxy device** (`nat=true`): the LAN hits `<this-host-ip>:<port>` and incus forwards it in. **Which host address it listens on follows the incus version**: >= 7.2 takes the wildcard `0.0.0.0` (every host address, `127.0.0.1` included); older daemons refuse a wildcard in `nat=true` mode - and a VM proxy has no non-NAT mode - so ivm names the host's current default-route IPv4 instead (that address ONLY, and the forward dies if the host's IP changes). `<port>` = same port both ends, or `<host-port>:<guest-port>` (docker `-p` style). Pins the VM's IPv4 first (the proxy needs a static target; pinned to the current lease, so no reboot - the same pin `ivm set static-ip` makes standalone). No arg lists the current forwards. Opens only that one port - for "VM as a full LAN host" you still need a bridge (see [incus-host-setup.md](docs/incus-host-setup.md)). |
| `unexpose [<host-port>]` | Remove a forward added by `expose`. No arg removes **all** of this VM's forwards (confirms; `--yes` skips). |
| `overwrite-dotfiles` | Re-push the host-staged dotfiles into the VM (no re-provision). |
| `set` / `unset` (no aspect) | List the configurable aspects (password / ssh-server / guest-shell-dir / host-bound-dir / user-sudo / git-ssh-key / static-ip) with one-line descriptions. Every aspect has both `set` and `unset`. |
| `set password <username>` / `unset password <username>` | Set (prompted, sent via stdin) / lock a guest account's login password (e.g. `user` for console/TTY login). Password only. |
| `set ssh-server <username> [--pubkey FILE]` / `unset ssh-server <username> [--pubkey FILE]` | Authorize / revoke key-based SSH login for a guest account (`user`/`root`) - e.g. for VS Code Remote-SSH. `set` appends `--pubkey` (repeatable; default `~/.ssh/id_ed25519.pub`) to that account's `authorized_keys` (idempotent - keeps keys you added by hand) and ensures sshd is up; `root` also gets `PermitRootLogin prohibit-password`. `unset` removes the key(s) (and root's override); leaves sshd running. Key-only, no password auth. Port/password tuning lives in the template's `sys.ssh_server`. |
| `set guest-shell-dir <path>` / `unset guest-shell-dir` | Set / clear the GUEST directory `ivm sh` starts in, inside the VM (the `user.ivm_shell_default_dir_after_login` tag; also set at `init` from a template's `shell_default_dir_after_login`). Only the interactive shell's start cwd - `$HOME` and a bare `cd` are unchanged. `<path>` is an absolute GUEST path; it need not exist yet (`ivm sh` warns + falls back to the default cwd if missing). `unset` reverts to incus's default cwd. |
| `set host-bound-dir [<path>]` / `unset host-bound-dir` | Bind / unbind the HOST dir that resolves this VM by cwd (the `user.ivm_host_bound_dir` tag). `set` with no path = the current dir; also the migration path for legacy VMs created before the tag. `unset` removes the tag - the VM is then targeted by name only. |
| `set user-sudo` / `unset user-sudo` | Opt `user` in / out of in-guest sudo: `user` may sudo, gated by ROOT's password (`Defaults:user rootpw`). Needs `set password root` first. `unset` removes the sudoers drop-in (back to the locked-down default). |
| `set git-ssh-key <keyfile> [--host HOST]` / `unset git-ssh-key [--host HOST]` | Copy a host **private** ssh key into the VM so in-guest `git` / `go get` reach **private** repos over SSH. Renamed to its type's default name (`id_ed25519`/`id_rsa`/...) so ssh auto-uses it (one key per VM); also trusts `--host` (default github.com) in known_hosts and sets git's `insteadOf` to rewrite `https`->`ssh` (needed for `go get`, which fetches via https). **WARNS + requires typing `yes i know`** (the key lives in the VM - use a low-value, passphrase-less, VM-only key); `--yes` does not skip it. `unset` removes the pushed key + the rewrite. |
| `set static-ip` / `unset static-ip` | Pin the VM's IPv4 to its **current** DHCP lease (incus eth0 `ipv4.address` = a static allocation in the bridge's DHCP server), so the address survives host/VM reboots - e.g. for a host-browser bookmark to an in-guest service like `vscode_web`. Same-address pin: nothing changes now, no reboot needed (the VM must be running with a lease). `expose` makes this pin implicitly (its proxy needs a fixed target); `set static-ip` is the standalone knob when host->guest over NAT is all you need. `unset` reverts to a dynamic lease that may change across reboots (refused while `expose` forwards target the pinned address - `unexpose` first). |
| `snapshot [create\|list\|restore\|delete] [name]` | Thin wrapper over `incus snapshot`, with the VM filled in. |
| `gui` | Open the VM's SPICE graphical console (`incus console --type=vga`), **detached** from the shell so you can close the terminal without killing it. Needs `remote-viewer` (virt-viewer) or `spicy` (spice-gtk) on the host + a desktop + `spice-vdagent` in the guest. |
| `env <template>` | Load + validate a template and print its resolved config (incl. the flattened package list). |

Before `stop` / `reboot` / `delete` interrupt a VM, `ivm` **loudly warns** if the guest
has live interactive sessions (an `ivm shell` / SSH login) the action would kill, then
asks. Best-effort (asks the guest for pty-owning processes); a stopped VM warns nothing.

### `--force`: when the VM is wedged in `Error` status

Incus reports `Error` when the VM's qemu process is still alive but incusd can no longer
reach its QMP (QEMU Machine Protocol - the socket incusd drives qemu through) monitor.
A plain restart then fails outright:

```
Error: The instance cannot be cleanly shutdown as in Error status
```

`ivm reboot --force` / `ivm stop --force` are the way out: incus SIGKILLs the qemu
process instead of asking the guest to shut down. **Guest writes not yet flushed to disk
are lost** (same as pulling the power), so `ivm` warns before its confirm prompt. A
common cause of `Error` is the storage pool running out of space - check `ivm
storage-status` before assuming the VM itself is at fault.

You do not have to recognise the state yourself: `start` / `stop` / `reboot` without
`--force` detect `Error` first and stop with the exact `ivm reboot --force <vm>` to run,
instead of firing an incus call that cannot succeed (and `stop` no longer mislabels such
a VM "already stopped").

## VM identity

`init` writes `user.ivm_init_at_dir=<cwd>` (pure historical record of where init
ran; also the managed-VM marker) and - for a bound template - `user.ivm_host_bound_dir`,
the tag resolution actually reads, from the template's required `host_bound_dir`
field (`$(pwd)` for project boxes). The cwd-resolved commands (`shell`, `start`,
`stop`, ...) find the VM whose `ivm_host_bound_dir` matches the current dir.
Run one from a SUBDIR of a bound project and `ivm` offers the nearest ancestor's
VM (`open '<vm>' bound at <parent>? [Y/n]`). The instance name is free-form (you
edit it at init); resolution is by the tag, not the name. `ivm cd <vm>` is the
inverse: it jumps the shell to that same bound dir by VM name. Re-bind anytime:
`ivm set host-bound-dir [<dir>]` (no arg = the current dir); `ivm unset
host-bound-dir` unbinds (removes the tag).

`host_bound_dir: ""` templates (the `llm_*` appliances) start unbound: `init`
writes NO binding tag, so the VM never resolves by cwd - target it by name from
anywhere (`ivm sh <vm>`, or `--name <vm>` for `snapshot`/`expose`/...; the
default name is a stable `ivm-<template>`). `ivm list` shows
`(unbound - reach by name)`; `ivm cd` refuses it. The no-match error lists every
unbound VM, but nothing ever auto-falls back to one; a legacy VM (created before
the tag existed) looks exactly the same - the error appends the copyable
`ivm --name <vm> set host-bound-dir <dir>` one-liner for any unbound VM whose
recorded init dir matches the current dir, which is how a legacy VM gets bound
once after upgrading.

## Provisioning model

`ivm` drives everything from the HOST via `incus exec` - the guest gets no
ansible/python. `init` does: `incus create` (stopped) -> attach devices (mounts +
`shadow` masks, `hw.tpm`, macvlan/bridge nic) -> `incus start` -> provision
(install baseline+groups+packages for the distro, set timezone + tmpfs, create
`user`, set both shells to zsh, write `~/.centralized-lang-pkgs/centralized-lang-pkgs.env.sh`
(redirects npm/pip/pipx/cargo/go global installs, same tree as the host's
`roles/centralize_lang_pkgs_dir`; thirdparty recipes source it), configure sshd,
run thirdparty recipes + `post_install_script` as root
- they drop to `user` via `su - user -c '...'` for user-scoped bits) -> push the
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
| Re-push dotfiles to every RUNNING managed guest (stopped ones are skipped, never auto-started) | `make vm-incus-push-dotfiles` |
| Remove `ivm` + the role's subdir (leaves VMs intact) | `make vm-incus-uninstall-ivm` |
| List managed VMs | `incus list user.ansible-managed=true` |

## Status / limitations

- Statically verified (mypy `--strict`, `ivm --dry-run`, `make vm-incus-sandbox`);
  real-incus end-to-end (launch / exec / virtio-fs) needs a real incus host.
- Windows tier (`os.type: windows`) is schema-defined but not yet implemented in
  `init` (linux only for now).
- No GPU acceleration (incus limitation; see hardware-capabilities doc).
