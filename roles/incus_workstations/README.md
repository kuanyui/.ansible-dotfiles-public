# roles/incus_workstations

Persistent Incus VM launchers, one VM per purpose. For things like Qt/C++ dev environment, Telegram-in-a-VM, browser-in-a-VM.

Different from [`roles/incus_agents`](../incus_agents/): one persistent VM per *purpose* (not per project), heavier resources, GUI-friendly, snapshot CLI baked in, apt-install happens ONCE at first `init` (not every time).

> Host-level concerns (which distros are supported, what gets installed on the host, the storage pool config matrix, CoW backends, openSUSE+snapper trap, moving the install tree, NAT vs bridge, virt-manager coexistence, `du` undercounting on loop-file pools) are all in [`roles/_incus_host_setup/README.md`](../_incus_host_setup/README.md). Those apply equally to this role and to `roles/incus_agents`.
>
> This file covers only what's specific to persistent workstation VMs.

## Quick start

1. Edit `roles/incus_workstations/defaults/main.yml` and uncomment / add an entry in `incus_workstations:`.
2. `make apply-incus-workstations`
3. `v-<name> init` (heavy first-time setup, may take minutes for big apt sets)
4. `v-<name> gui` if you set `gui: true` (opens SPICE in `virt-viewer`)
5. `v-<name> snapshot create <snap>` before risky changes

## What's in the VM

- **Base**: Debian 13 minimal (override per-entry via `base_image`)
- **Default shell**: zsh
- **Common apt packages** (always installed at first `init`):
  `openssh-server`, `curl`, `git`, `ca-certificates`, `sudo`, `zsh`, `zsh-syntax-highlighting`, `zsh-autosuggestions`, `tmux`
- **Per-entry apt packages**: whatever you put in `apt_packages:` (e.g. `qtcreator`, `task-lxde-desktop`, `spice-vdagent`, ...)
- **Dotfiles**: `~/.bashrc`, `~/.zshrc`, `~/.tmux.conf` (same staging as `roles/incus_agents`, pushed at first `init` and on `update`)
- **Mounts**: whatever you put in `mounts:` (host path → VM path, virtio-fs share, idmap-shifted to UID 1000)

## Schema

Per `incus_workstations[*]` entry:

| Field | Required | Default | What it does |
|---|---|---|---|
| `name` | yes | - | Launcher = `v-<name>`. VM = `v-<name>`. |
| `display_name` | no | `name` | Shown in `help` / `env`. |
| `apt_packages` | yes | - | Distro packages installed at first `init`. May be empty list. |
| `base_image` | no | `images:debian/13` | Incus image to launch VM from. |
| `cpu` / `memory` / `disk` | no | 4 / 8GiB / 30GiB | VM resource overrides. |
| `gui` | no | `false` | Enable the `gui` subcommand (SPICE display). |
| `mounts` | no | `[]` | List of `{host, target}` virtio-fs shares. |

## Launcher subcommands

| Subcommand | What it does |
|---|---|
| `help` | Show usage |
| `env` | Show resolved config |
| `init` | Create VM, mount shares, run first-time setup (apt + dotfiles), mark provisioned. Idempotent: subsequent runs only start the VM. |
| `start` | Start VM if stopped |
| `stop` | Stop VM (state preserved) |
| `shell` | zsh into VM as `user`, cwd = `/home/user` |
| `gui` | Open SPICE display (needs `virt-viewer` / `remote-viewer` on host). Only if `gui: true`. |
| `update` | Force-refresh: apt update + upgrade + reinstall `apt_packages`, re-push dotfiles. Use after editing host dotfiles + re-apply. |
| `snapshot create <name>` | Create VM snapshot |
| `snapshot list` | List snapshots of this VM |
| `snapshot restore <name>` | Roll VM back to snapshot |
| `snapshot delete <name>` | Delete a snapshot |
| `rma` | rm all: delete VM + disk + snapshots |

## Idempotence model

Unlike `roles/incus_agents` (where every `v-<agent> init` re-runs apt + dotfiles push), workstations gate the heavy setup on a marker file `/etc/.ansible-workstation-provisioned` inside the VM:

- **First `init`** : apt install + dotfiles push + create marker → ~minutes
- **Subsequent `init`** : just `incus start` + wait → seconds
- **`update`** : ignores marker, re-runs apt update+upgrade + re-pushes dotfiles → ~minutes

This avoids surprising re-apt every time you bring the VM up.

## GUI: SPICE display

`v-<name> gui` is a thin wrapper around `incus console --type=vga <VM>`. Incus will auto-spawn `virt-viewer` (preferred) or `remote-viewer` on the host. You need ONE of those installed:

- Debian / Ubuntu: `sudo apt install virt-viewer`
- Fedora: `sudo dnf install virt-viewer`
- openSUSE: `sudo zypper install virt-viewer`

Inside the VM you also need:
- a desktop environment or window manager (e.g. `task-lxde-desktop`, `xfce4`)
- `spice-vdagent` package (clipboard sharing, dynamic resolution)

Add those to the entry's `apt_packages:` (the example entries in `defaults/main.yml` show what works).

## Adding / removing mounts post-hoc

The `mounts:` field in your entry is only consulted at **first-time VM creation**. Once the VM exists, edits to `mounts:` (followed by `apply-incus-workstations`) only re-render the launcher script — the VM's actual attached devices are NOT touched.

To add or remove mounts on an already-existing VM, talk to Incus directly. Both work on a **running** VM (no shutdown needed, no guest fstab edit needed - `incus-agent` inside the VM auto-mounts via virtio-fs):

```sh
# add a new mount (host dir -> VM /workspaces/foo)
incus config device add v-qtdev workspace_foo disk \
    source=$HOME/some/path \
    path=/workspaces/foo \
    shift=true

# list what's currently attached
incus config device list v-qtdev

# remove a mount (use the device name from `device list`, NOT the path)
incus config device remove v-qtdev workspace_foo
```

Device config is stored in Incus's database, so the mount survives `stop` / `start` cycles. The `shift=true` flag ensures host UID 1000 == VM UID 1000 (the `user` account inside the VM), so files appear with sensible ownership.

## Snapshots

Snapshot cost depends on the storage pool backend (set at first-time `incus admin init`):

| Backend | Cost |
|---|---|
| `dir` (this project's default) | full copy, slow, doubles disk per snapshot |
| `btrfs` / `zfs` / `lvm-thin` | CoW reference, instant, near-zero space |

If you'll routinely snapshot, switch the pool backend to `btrfs` / `zfs`. See [Configuring the storage pool](../_incus_host_setup/README.md#configuring-the-storage-pool) in `_incus_host_setup` README for the var matrix and how to relocate.

## Name collision with `roles/incus_agents`

Both roles drop launchers at `~/.local/bin/v-<name>`. **Don't use the same `name` in `incus_apps[*]` and `incus_workstations[*]`** — the second one to apply overwrites the first one's launcher.

Pick names that signal which role they belong to:
- Agents: `claude`, `codex` (LLM agent names)
- Workstations: `qtdev`, `tg`, `firefox`, `vlc`, `wireshark` (purpose / app names)

No automatic cross-role check exists yet (each role has its own manifest).

## Where files live

| What | Default path |
|---|---|
| Launcher script | `~/.local/bin/v-<name>` |
| zsh completion | `~/.local/share/ansible-managed/incus-workstations/zsh-completions/_v-<name>` |
| bash completion | `~/.local/share/ansible-managed/incus-workstations/bash-completions/v-<name>` |
| Install manifest | `~/.local/share/ansible-managed/incus-workstations/incus-workstations.manifest.yml` |
| Staged VM dotfiles | `~/.local/share/ansible-managed/incus-workstations/vm-rootfs/home/user/` |
| VM disk (incus default) | `/var/lib/incus/storage-pools/default/virtual-machines/v-<name>/root.img` |
| VM snapshots (incus default) | `/var/lib/incus/storage-pools/default/virtual-machines-snapshots/v-<name>/<snap>/` |

For deeper storage layout (image cache, CoW backends, openSUSE + snapper trap, moving the whole `/var/lib/incus/` tree), see [`roles/_incus_host_setup/README.md`](../_incus_host_setup/README.md). Both face roles share host-level setup via that internal role.

## Cleanup

| What | Command |
|---|---|
| Stop one VM | `v-<name> stop` |
| Delete one VM (config + disk + snapshots) | `v-<name> rma` |
| Remove launchers + manifest (leaves VMs intact) | `make unapply-incus-workstations` |
| List all workstation VMs | `incus list ^v-` (also shows agents - check by name) |

## TODOs / known limitations

- **Single-distro**: launcher's apt commands are Debian-only. If you set `base_image: images:fedora/43` or similar in an entry, the first-`init` apt step will fail. TODO: parse `base_image` at render time + emit `apt` / `dnf` / `zypper` accordingly.
- **GUI scope**: only `incus console --type=vga` (SPICE full-VM display). No per-app Wayland / X11 forwarding yet.
- **No cross-role name check**: agents and workstations can collide on `v-<name>`. User is responsible.
- **Sandbox**: round-trip works with empty `incus_workstations: []` (the default). For real-launcher coverage, override via `-e` or uncomment defaults examples.
