# roles/incus_agents

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
- **Dotfiles**: `~/.bashrc`, `~/.zshrc`, `~/.tmux.conf` (rendered host-side at `apply-incus-agents` time, synced into the VM on every `init` - idempotent, so editing host dotfiles + re-`apply-incus-agents` + next `v-<agent> init` propagates changes into all VMs)
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
| Staged dotfiles (host) | `~/.local/share/ansible-managed/incus_agents/vm-rootfs/home/user/` | <100 KB |

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

## Q&A

### Where do cached incus images, per-VM disk files, installer ISOs, and snapshots live? Can the paths be changed?

Three things called "image" in this stack, do not conflate them:

- **Cached incus image** - a tarball fetched from a remote (e.g. `images:`); for VMs it bundles a pre-built qcow2 disk + metadata. One per fingerprint, shared by every VM launched from it.
- **Per-VM disk file** - a qcow2 file (`root.img`), one per VM, copied out of the cached incus image at `incus launch` time. This is what the VM actually boots from and writes to.
- **Installer ISO** - bootable install media (`.iso`). Not used by `incus launch images:*`; only relevant if you import one yourself.

All three plus snapshots live under `/var/lib/incus/`:

| What | Default path |
|---|---|
| Cached incus image (tarball: qcow2 + metadata) | `/var/lib/incus/images/` |
| Per-VM disk file (qcow2, `dir` backend) | `/var/lib/incus/storage-pools/<pool>/virtual-machines/<vm>/root.img` |
| Per-VM snapshot (`dir` backend) | `/var/lib/incus/storage-pools/<pool>/virtual-machines-snapshots/<vm>/<snap>/` |
| Installer ISO (only if you imported one) | inside the storage pool you targeted via `incus storage volume import --type=iso` |

What `incus launch images:debian/13` pulls is a cached incus image, NOT an installer ISO - this is incus's normal install path: copy the cached qcow2 into a per-VM disk file, boot it, done.

If you actually need to run an installer ISO (custom install, niche distro):

```sh
incus storage volume import default debian-13.iso debian13-installer --type=iso
```

Safer source for VM disk images than raw `curl` of an ISO: `virt-builder` (from `guestfs-tools`, the Red Hat / libguestfs toolkit; maintained at libguestfs.org since 2009) downloads + GPG-verifies upstream pre-built qcow2 disks. This role installs `guestfs-tools` for you on Debian / Fedora / openSUSE (same package name on all three since libguestfs split tools out in 2022). Then `incus image import` to register the result as a cached incus image, or `incus storage volume import` to attach it as a one-off disk.

Customizable:
- whole tree: symlink `/var/lib/incus` elsewhere (see [Move everything](#move-everything-image-cache--pool--db))
- per-pool storage path: `incus_storage_pool_source` at first init, or `incus storage create <pool> dir source=/path` post-init
- cached-image directory: not movable separately - it tracks wherever `/var/lib/incus/` points

### ext4, btrfs noCoW, or btrfs - which for VM disks?

Depends on the incus storage backend:

| Backend | Best FS | Why |
|---|---|---|
| `dir` (this role's default) | ext4 / xfs | predictable, no double-CoW |
| `dir` | btrfs + `chattr +C` on the storage dir | disables CoW per-file |
| `btrfs` | btrfs | incus uses subvolumes + reflinks, manages CoW at the right level |
| `zfs` | zfs | same idea on zvol |

Bad combo: `dir` backend on plain btrfs (no `chattr +C`). qcow2 random writes amplify under btrfs CoW; `du` balloons; fragmentation hurts I/O. The role's `host_setup.yml` warns about this; the `openSUSE + snapper trap` section above covers a related failure mode.

### Does incus conflict with virt-manager? Can virt-manager see incus VMs?

No conflict, no visibility either.

- incus invokes QEMU directly; virt-manager goes through libvirt. Two separate stacks, sharing only `/dev/kvm`.
- virt-manager does NOT list incus VMs (and incus does not list libvirt VMs).
- Default networks do not overlap: libvirt `virbr0` = `192.168.122.0/24`, incus `incusbr0` = an auto-picked subnet.
- Both stacks add their own nftables rules. Usually harmless.

### How to pick NAT vs Bridge for a VM?

This role's default: NAT via the managed bridge `incusbr0` (built-in DHCP + DNS + outbound NAT, host-only - VMs reach the internet, the LAN does not reach VMs).

Switch one VM to LAN-bridged:

```sh
# A) macvlan: no host setup, but host <-> VM is blocked by macvlan kernel limit
incus config device override <vm> eth0 nictype=macvlan parent=<host-nic>

# B) real Linux bridge (host must have `br0` set up via NetworkManager/netplan first): host <-> VM works
incus config device override <vm> eth0 nictype=bridged parent=br0
```

Restore NAT on a single VM:

```sh
incus config device override <vm> eth0 network=incusbr0
```

Apply to every new VM: edit the `default` profile, or create a separate profile and assign it at launch.
