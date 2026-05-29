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
| Base image cache (always on `/`) | `/var/lib/incus/images/<sha>` | ~1 GB each |
| Daemon state (always on `/`) | `/var/lib/incus/database/` | ~10 MB |
| Pool blocks (project default = btrfs loop on `/home`) | `/home/incus-storage.img` (sparse, declared 500GiB) | grows with VM writes |
| VM root disks (mount-view, regardless of backend) | `/var/lib/incus/storage-pools/default/virtual-machines/<vm>/` | depends on backend, see CoW table below |
| Staged dotfiles (host) | `~/.local/share/ansible-managed/incus_agents/vm-rootfs/home/user/` | <100 KB |

Image is downloaded **once** per remote source. Every VM created from it gets its own root disk. For the full table of where each data kind lands under each storage pool config, see [Where do cached images, VM disks, ISOs, snapshots live?](#where-do-cached-incus-images-per-vm-disk-files-installer-isos-and-snapshots-live-can-the-paths-be-changed) in Q&A.

## CoW: how disk grows with N VMs

Same `images:debian/13`, 10 different projects:

| Backend | Per-VM disk | 10 VMs total | When to pick |
|---|---|---|---|
| `dir` | full ~1 GB copy | ~11 GB | works on any FS, no setup; Incus's built-in default |
| **`btrfs`** (this role's default, via loop file on `/home`) | few MB + writes | ~2-3 GB | want CoW snapshots; no btrfs partition needed (loop file inside ext4 `/home` is fine) |
| `zfs` | few MB + writes | ~2-3 GB | host has ZFS |
| `lvm-thin` | few MB + writes | ~2-3 GB | host has an LVM thin pool already configured |

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

## Configuring the storage pool

Three vars in [`roles/_incus_host_setup/defaults/main.yml`](../_incus_host_setup/defaults/main.yml) drive the preseed pool config. Set in `host_vars/<hostname>.yml`. Effective ONLY at first-time `incus admin init --preseed`:

| Var | Project default | Meaning |
|---|---|---|
| `incus_storage_pool_driver` | `btrfs` | backend: `dir` / `btrfs` / `zfs` / `lvm-thin` |
| `incus_storage_pool_source` | `/home/incus-storage.img` | dir path / btrfs subvol / image file / LV name (see below) |
| `incus_storage_pool_size` | `500GiB` | only for loop-file backends (btrfs / zfs creating an image) |

### Why `btrfs` loop file on `/home` as the default?

The project targets hosts where `/` is a small btrfs system partition (often ~160-180 GB on openSUSE / Tumbleweed installs) and `/home` is a much larger ext4 partition. Putting Incus VM disks directly on `/` runs it out of space fast; putting them on `/home` with btrfs in a loop file gets us CoW snapshots without repartitioning. The loop file is sparse - actual `/home` usage starts near zero and grows as VMs write. Tradeoff vs a real btrfs partition: ~5-10% overhead (ext4 → loop → btrfs).

### Overrides (in `host_vars/<hostname>.yml`)

**Use Incus's built-in default** (dir on `/`, no CoW; only when `/` has plenty of space):

```yaml
incus_storage_pool_driver: dir
incus_storage_pool_source: ""
incus_storage_pool_size: ""
```

**Sidecar disk mounted at `/data`** (no CoW, simplest):

```yaml
incus_storage_pool_driver: dir
incus_storage_pool_source: /data/vm/incus
incus_storage_pool_size: ""
```

**Already-set-up ZFS dataset**:

```yaml
incus_storage_pool_driver: zfs
incus_storage_pool_source: tank/incus    # ZFS dataset name, no leading /
incus_storage_pool_size: ""
```

### Post-init changes

The preseed task is gated to ONLY fire when the `default` pool doesn't exist yet. To change layout after init:

```sh
# (1) create a second pool with the new layout
incus storage create archive btrfs source=/home/incus-archive.img size=200GiB

# (2) move a VM to it
incus stop v-claude-proj
incus move v-claude-proj v-claude-proj --storage archive
incus start v-claude-proj

# (3) optional: delete the old pool once empty
incus storage delete default
```

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
- **Per-VM disk file** - one per VM, created from the cached image at `incus launch` time. Format depends on storage pool backend (qcow2 file for `dir`, btrfs subvolume for `btrfs`, ZFS dataset for `zfs`, thin LV for `lvm-thin`). This is what the VM actually boots from and writes to.
- **Installer ISO** - bootable install media (`.iso`). Not used by `incus launch images:*`; only relevant if you import one yourself.

#### Always on `/` (daemon-level, NOT affected by storage pool config)

| What | Path |
|---|---|
| Cached incus image (tarball: qcow2 + metadata) | `/var/lib/incus/images/<fingerprint>/` |
| Daemon database + server certs | `/var/lib/incus/database/`, `/var/lib/incus/server.crt`, ... |
| Daemon config | `/etc/incus/` |
| Logs | `/var/log/incus/` |

These move only if you symlink `/var/lib/incus` whole (see [Move everything](#move-everything-image-cache--pool--db)).

#### Pool-level data (depends on `incus_storage_pool_{driver,source,size}`)

`<pool>` below = `/var/lib/incus/storage-pools/default/` — the **mount point** where Incus exposes the `default` pool, regardless of backend. For `dir` backend that's also where the actual files live; for loop-file backends, that mount points INTO the loop file's filesystem.

| | **`btrfs` loop on `/home`**<br>(project default) | **`dir` on `/`**<br>(Incus's built-in default) | **`dir` on `/data`** | **`zfs` loop on `/home`** |
|---|---|---|---|---|
| `defaults/main.yml` config | `driver: btrfs`<br>`source: /home/incus-storage.img`<br>`size: 500GiB` | `driver: dir`<br>`source: ""`<br>`size: ""` | `driver: dir`<br>`source: /data/vm/incus`<br>`size: ""` | `driver: zfs`<br>`source: /home/incus-storage.zfs`<br>`size: 500GiB` |
| Pool blocks physically live in | `/home/incus-storage.img` (sparse loop file, btrfs FS inside) | inside `/` filesystem, at `<pool>/` directly | inside `/data` filesystem, at `/data/vm/incus/` directly | `/home/incus-storage.zfs` (sparse loop file, ZFS pool inside) |
| Per-VM root disk | btrfs subvol, CoW-cloned from pool template | full qcow2 file at `<pool>/virtual-machines/<vm>/root.img` | full qcow2 at `/data/vm/incus/virtual-machines/<vm>/root.img` | ZFS dataset, CoW clone of pool template |
| Per-VM snapshot | btrfs subvol snapshot — instant, ~0 space | full dir copy at `<pool>/virtual-machines-snapshots/<vm>/<snap>/` — slow, doubles disk | full dir copy at `/data/vm/incus/virtual-machines-snapshots/<vm>/<snap>/` | ZFS snapshot — instant, ~0 space |
| Pool template (image clone src) | btrfs subvol at `<pool>/images/<fp>` (inside loop) | none (`dir` backend has no template; each VM is a fresh full copy of the daemon-level cached image) | none (same as above) | ZFS dataset `default/images/<fp>` |
| Imported ISO (custom volume) | custom volume in pool (inside loop) | `<pool>/custom/iso/<volname>/` (real dir on `/`) | `/data/vm/incus/custom/iso/<volname>/` | ZFS dataset under pool |
| CoW snapshots cheap? | **yes** (btrfs reflinks) | no (full copy each time) | no | **yes** (ZFS snapshots) |

#### Reading the table

- Even with the loop-file backends, `incus list` / `incus storage info default` reports paths under `<pool>` (= `/var/lib/incus/storage-pools/default/`). That's the MOUNT view. The actual blocks are inside the `source:` loop file on `/home`.
- `du -sh /var/lib/incus/` will UNDERCOUNT for loop-file backends because the pool's contents live in the loop file on `/home`, not on `/`. Use `du -sh /home/incus-storage.img` (or `incus storage info default`) for real usage.
- For `dir`-on-`/` (Incus built-in default), `<pool>` IS the real path, so `du -sh /var/lib/incus/` counts everything.

#### Installer ISO (rare path)

What `incus launch images:debian/13` pulls is a cached incus image, NOT an installer ISO - this is incus's normal install path: clone the cached image into a per-VM disk file, boot it, done.

If you actually need to run an installer ISO (custom install, niche distro):

```sh
incus storage volume import default debian-13.iso debian13-installer --type=iso
```

Safer source for VM disk images than raw `curl` of an ISO: `virt-builder` (from `guestfs-tools`, the Red Hat / libguestfs toolkit; maintained at libguestfs.org since 2009) downloads + GPG-verifies upstream pre-built qcow2 disks. This role installs `guestfs-tools` for you on Debian / Fedora / openSUSE (same package name on all three since libguestfs split tools out in 2022). Then `incus image import` to register the result as a cached incus image, or `incus storage volume import` to attach it as a one-off disk.

#### What can be moved where

- **Whole tree** (cached images + pool + DB + config): symlink `/var/lib/incus` elsewhere — see [Move everything](#move-everything-image-cache--pool--db).
- **Per-pool blocks** (where the VMs / snapshots / pool template actually live): `incus_storage_pool_{driver,source,size}` at first init (see [Configuring the storage pool](#configuring-the-storage-pool)), or `incus storage create <pool> <driver> source=... [size=...]` post-init.
- **Cached-image directory**: not movable separately - it always lives under wherever `/var/lib/incus/` points.

### ext4, btrfs noCoW, or btrfs - which for VM disks?

Depends on the incus storage backend:

| Backend | Best FS | Why |
|---|---|---|
| `dir` | ext4 / xfs | predictable, no double-CoW |
| `dir` | btrfs + `chattr +C` on the storage dir | disables CoW per-file |
| `btrfs` (this role's default, via loop file) | btrfs | incus uses subvolumes + reflinks, manages CoW at the right level. Loop file on ext4 `/home` works because the btrfs layer only sees its own block device |
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
