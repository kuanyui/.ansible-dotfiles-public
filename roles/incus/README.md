# roles/incus

Per-project KVM VM launchers. One VM per `(agent, project)`.

Stronger isolation than `c-<agent>-<runtime>` rootless containers: separate kernel, virtio-fs share via standalone `virtiofsd`.

## Quick start

```sh
cd ~/project              # any project dir
v-claude init             # create VM + install claude (first time only, ~30-60s)
v-claude claude           # run claude inside the VM
v-claude shell            # ssh into the VM (zsh, cwd = /workspaces/<project>)
v-claude rma              # delete this VM
```

VM name = `v-<agent>-<projectname>`. Different projects get different VMs.

## What's inside the VM

- **Base**: Debian 13 minimal
- **Default shell**: zsh
- **apt packages** installed at `init`:
  - common: `openssh-server`, `curl`, `git`, `ca-certificates`, `sudo`, `zsh`, `zsh-syntax-highlighting`, `zsh-autosuggestions`, `tmux`
  - codex only: `nodejs`, `npm`
- **Agent binary**:
  - claude → `curl -fsSL https://claude.ai/install.sh | bash`
  - codex → `npm install -g @openai/codex`
- **Dotfiles**: `~/.bashrc`, `~/.zshrc`, `~/.tmux.conf` (rendered host-side at `apply-incus` time, pushed in at first `init`)
- **Your project dir**: virtio-fs shared at `/workspaces/<projectname>`. `shift=true` maps host UID 1000 ↔ VM UID 1000, so files appear as `user`, not `nobody`.

## How `v-claude init` works

1. Launcher reads `$PWD`, derives `PROJECT_NAME` and `VM_NAME` (`v-<agent>-<projectname>`)
2. If VM missing: `incus launch images:debian/13 <vm> --vm --config limits.cpu=4 --config limits.memory=4GiB --device root,size=10GiB`
3. Wait up to 90s for `incus-agent` inside the VM
4. Attach virtio-fs: host project dir → `/workspaces/<projectname>` (with `shift=true`)
5. apt install + create `user` (UID 1000) + chsh to zsh
6. `incus file push --recursive` staged dotfiles → `/home/user/`
7. Curl-install or npm-install the agent inside the VM
8. Done. Re-running `init` is idempotent.

## Where files live

| What | Default path | Size |
|---|---|---|
| Base image cache | `/var/lib/incus/images/<sha>` | ~1 GB each |
| VM root disks | `/var/lib/incus/storage-pools/default/virtual-machines/<vm>/root.img` | depends on backend (below) |
| Daemon state | `/var/lib/incus/database/` | ~10 MB |
| Staged dotfiles (host) | `~/.local/share/ansible-managed/incus/vm-rootfs/home/user/` | <100 KB |

Image is downloaded **once** per remote source. Every VM created from it gets its own root disk.

## CoW: how disk grows with N VMs

Same `images:debian/13`, 10 different projects:

| Backend | Per-VM disk | 10 VMs total | When to pick |
|---|---|---|---|
| **`dir`** (this role's default) | full ~1 GB copy | ~11 GB | works on any FS, no setup |
| `btrfs` | few MB + writes | ~2-3 GB | btrfs FS (openSUSE etc) |
| `zfs` | few MB + writes | ~2-3 GB | zfs FS |
| `lvm-thin` | few MB + writes | ~2-3 GB | LVM thin pool |

`dir` is universal but uses N× the disk. Switch to `btrfs` / `zfs` if you run >5 VMs.

Backend is chosen at first-time `incus admin init`. Changing later needs a manual re-init (this role won't redo it).

## Snapshots

This role does NOT auto-snapshot. Use Incus directly:

```sh
incus snapshot create v-claude-foo before-update
incus snapshot list v-claude-foo
incus snapshot restore v-claude-foo before-update
incus snapshot delete v-claude-foo before-update
```

Snapshot cost depends on backend:
- `dir`: full copy. Slow. Doubles disk per snapshot.
- `btrfs` / `zfs` / `lvm-thin`: CoW reference. Instant. Near-zero space.

## openSUSE + snapper trap (btrfs backend only)

Combining `btrfs` Incus backend with snapper on `/` can desync:

- snapper rolls back `@/` (incus database lives under it)
- VM disks are SEPARATE btrfs subvolumes, NOT inside `@/`, NOT in the snapper snapshot
- result: DB says "VMs X, Y exist", disk has Y, Z. Reconcile by hand.

Fixes (pick one, manual):
- exclude `/var/lib/incus/` from snapper config
- put `/var/lib/incus/` on its own subvolume
- put incus on a different filesystem
- OR stay on `dir` backend (no subvolumes, no interaction)

## Move VM disks elsewhere

Useful if `/` is small. Effective only at first-time `incus admin init`:

```yaml
# host_vars/<hostname>.yml
incus_storage_pool_source: /data/vm/incus
```

For a post-init move: use `incus storage create <new-pool>` and migrate VMs by hand.

## Move everything (image cache + pool + DB)

One symlink, manual:

```sh
sudo systemctl stop incus
sudo mv /var/lib/incus /target/path/incus-state
sudo ln -s /target/path/incus-state /var/lib/incus
sudo systemctl start incus
```

## Inspecting

```sh
incus list                                  # all VMs
incus list --columns ns,disk_usage          # disk per VM
incus image list                            # cached images
incus storage list                          # pools + backend
sudo du -sh /var/lib/incus/*                # raw breakdown
```

## Cleanup

| What | Command |
|---|---|
| One VM | `v-<agent> rma` |
| One cached image | `incus image delete <fingerprint>` |
| All unused images | wait 10 days OR lower `images.remote_cache_expiry` in preseed |
| Nuke everything | `sudo systemctl stop incus && sudo rm -rf /var/lib/incus/* && sudo systemctl start incus` |
