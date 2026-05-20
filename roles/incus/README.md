# roles/incus — storage layout

## Two independent paths

| | Path (default) | Controlled by | Size grows with |
|---|---|---|---|
| **Image cache** (downloaded base images, e.g. `images:debian/13`) | `/var/lib/incus/images/<sha256>` | not configurable from this role; baked into Incus daemon | # of distinct base images (~500 MB-1 GB each) |
| **Storage pool** (per-VM root disks) | `/var/lib/incus/storage-pools/default/virtual-machines/<vm>/root.img` | `incus_storage_pool_source` var | # of VMs × backend behavior (see below) |

Daemon metadata (`/var/lib/incus/database/`) is small (~10 MB), ignored hereafter.

## How a base image is reused across N VMs

When you `v-claude init` from the same `images:debian/13` for N different projects, what happens depends on the **pool's backend**:

| Backend | `init` behavior | Disk per VM | Total for N VMs (image + N disks) |
|---|---|---|---|
| **`dir`** (this role's default) | Full file copy from image cache → VM dir | full image (~1 GB) + writes | ~1 GB + N × ~1 GB |
| `btrfs` | btrfs subvolume snapshot of image | ~few MB initial + writes only | ~1 GB + N × few MB |
| `zfs` | ZFS clone of image dataset | ~few MB initial + writes only | ~1 GB + N × few MB |
| `lvm-thin` | Thin-provisioned LV snapshot | similar to btrfs/zfs | similar |

**The base image is downloaded once regardless of backend.** What differs is whether the per-VM root disk is a copy (`dir`) or a CoW reference (`btrfs`/`zfs`/`lvm-thin`).

This role's preseed defaults to **`dir`** because it works on any filesystem without extra setup. If you'll routinely run >5 VMs from the same image, switch to `btrfs` or `zfs` backend (manual `incus admin init` re-run; this role doesn't change pool backends after first init).

## Disk usage example (10 VMs from debian/13)

| | dir backend | btrfs backend |
|---|---|---|
| Image cache | ~1 GB | ~1 GB |
| 10× VM root.img | ~10 GB | ~1-2 GB (shared blocks) |
| **Total** | **~11 GB** | **~2-3 GB** |

## btrfs backend & snapper interaction (openSUSE / Tumbleweed users)

Incus's **`btrfs` backend does NOT use qcow2**. Each VM is a btrfs subvolume snapshot of the image template's subvolume; inside, the raw `root.img` has `chattr +C` (NODATACOW) so per-write amplification is avoided. This sidesteps the classic "qcow2 + btrfs CoW = bad" trap.

But there's a different trap if you put Incus on `/` btrfs alongside snapper:

| Path under `/var/lib/incus/` | btrfs status | In `snapper snapshot @/`? |
|---|---|---|
| `database/`, `server.crt`, daemon configs | regular files | ✅ yes |
| `storage-pools/default/` | subvolume | ❌ no (btrfs snapshots don't recurse into child subvolumes) |
| `storage-pools/default/virtual-machines/<vm>/` | subvolume | ❌ no |
| `images/<sha>/` | subvolume | ❌ no |

After `snapper rollback`: the daemon database rolls back to its old state, but the actual VM subvolumes do not. Result: Incus's database says "VMs X, Y exist" while the disk has VMs Y, Z. Desync, manual reconcile needed.

Workarounds if you want both Incus btrfs backend AND snapper on the same `/`:
- (a) exclude `/var/lib/incus/` from snapper's config (snapper-side)
- (b) make `/var/lib/incus/` its own subvolume so snapper of `@/` doesn't include the database either (cleaner, but advanced btrfs setup)
- (c) put Incus on a different btrfs filesystem (separate partition or loopback btrfs image) that snapper doesn't manage

This role doesn't auto-configure any of those. If you're using snapper, either stay on `dir` backend (no subvolumes, no interaction) or pick one of the workarounds manually before switching the pool to btrfs.

## Customizing locations

### Move just the storage pool (recommended)

Put VM disks on a different filesystem; leave image cache + daemon state on `/`:

```yaml
# host_vars/<hostname>.yml
incus_storage_pool_source: /data/vm/incus
```

Takes effect at first-time `incus admin init` only. Already-initialized incus is NOT re-pointed by this var — if you want to move pools post-init, use `incus storage create <new-pool>` and migrate VMs manually.

### Move everything (image cache + storage pool + database)

One symlink, done manually (not by this role):

```sh
sudo systemctl stop incus
sudo mv /var/lib/incus /target/path/incus-state
sudo ln -s /target/path/incus-state /var/lib/incus
sudo systemctl start incus
```

Useful if `/` is small. Bind-mount via `/etc/fstab` is also fine if you don't like symlinks.

## Inspecting what's actually on disk

```sh
incus storage list                          # pools + backend + used/total
incus storage info default                  # one pool's details
incus image list                            # all cached images with size
incus list --columns ns,disk_usage          # per-VM disk usage
sudo du -sh /var/lib/incus/*                # raw breakdown
sudo du -sh /var/lib/incus/images/          # image cache total
```

## Cleanup

| What | Command |
|---|---|
| One specific VM | `v-<agent> rma` (calls `incus delete -f`) |
| Specific cached image | `incus image delete <fingerprint>` |
| All unused images (older than auto-expire) | wait 10 days, or set `images.remote_cache_expiry` lower in `incus admin init` preseed |
| Wipe everything (nuclear) | `sudo systemctl stop incus && sudo rm -rf /var/lib/incus/* && sudo systemctl start incus` |
