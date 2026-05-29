# roles/_incus_host_setup

Internal sub-role - shared host-level prep for any incus-using face role (`roles/incus_agents`, `roles/incus_workstations`, future ones too). NOT a standalone playbook entry point; called via `include_role: _incus_host_setup` from each face role.

This README covers everything that is **independent of which face role you're using**: supported distros, what gets installed on the host, the `default` storage pool config matrix, the openSUSE+snapper btrfs trap, moving incus data around post-install, host-level inspecting / cleanup, and the network / virt-manager FAQs.

Face-role-specific docs:
- LLM agent VMs (ephemeral, per `(agent, project)`): [`roles/incus_agents/README.md`](../incus_agents/README.md)
- Persistent purpose VMs (one per use case, GUI-capable, snapshots): [`roles/incus_workstations/README.md`](../incus_workstations/README.md)

## What this role does on the host

- Asserts host distribution is one of: Fedora 43+ / Debian trixie+ (or bookworm-backports) / openSUSE Tumbleweed / openSUSE Leap 15.6+ (those are the distros that ship `incus` in their official repo). Escape hatch per face role: `<face_role>_skip_host_setup: true`.
- Installs `incus` package + `guestfs-tools` (provides `virt-builder` for GPG-verified VM disk image fetch).
- Probes `incus.service`; starts + enables if not active.
- Adds `$USER` to `incus-admin` group (re-login required for membership to take effect).
- Probes `/` filesystem type; warns about the `qcow2 + btrfs CoW` trap when defaulting to `dir` backend on a btrfs `/`.
- Runs `incus admin init --preseed` exactly once (only if the `default` storage pool doesn't already exist).

All steps gated on no-`become` probes - on a fully-set-up host this whole role is a no-op that doesn't even prompt for sudo.

## CoW: how disk grows with N VMs

Same `images:debian/13`, 10 different projects:

| Backend | Per-VM disk | 10 VMs total | When to pick |
|---|---|---|---|
| `dir` | full ~1 GB copy | ~11 GB | works on any FS, no setup; Incus's built-in default |
| **`btrfs`** (this project's default, via loop file on `/home`) | few MB + writes | ~2-3 GB | want CoW snapshots; no btrfs partition needed (loop file inside ext4 `/home` is fine) |
| `zfs` | few MB + writes | ~2-3 GB | host has ZFS |
| `lvm-thin` | few MB + writes | ~2-3 GB | host has an LVM thin pool already configured |

Backend is chosen at first-time `incus admin init`. Changing later needs a manual re-init (this role won't redo it - see [Post-init changes](#post-init-changes) below).

## Snapshots - backend cost matrix

This role does NOT auto-snapshot. Each face role exposes its own snapshot UX (agents: bare `incus snapshot` commands; workstations: launcher's built-in `v-<name> snapshot ...` wrapper). Cost depends purely on backend:

| Backend | Snapshot cost |
|---|---|
| `dir` | full directory copy, slow, doubles disk per snapshot |
| `btrfs` / `zfs` / `lvm-thin` | CoW reference, instant, near-zero space |

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

Note: this project's default uses btrfs LOOP FILE on `/home` (not a btrfs subvolume of `/`), so the snapper trap doesn't apply to the default config - snapper doesn't snapshot `/home`'s loop file contents because they're inside a single file from snapper's perspective.

## Configuring the storage pool

Three vars in [`defaults/main.yml`](defaults/main.yml) drive the preseed pool config. Set in `host_vars/<hostname>.yml`. Effective ONLY at first-time `incus admin init --preseed`:

| Var | Project default | Meaning |
|---|---|---|
| `incus_storage_pool_driver` | `btrfs` | backend: `dir` / `btrfs` / `zfs` / `lvm-thin` |
| `incus_storage_pool_source` | `/home/incus-storage.img` | dir path / btrfs subvol / image file / LV name (see below) |
| `incus_storage_pool_size` | `500GiB` | only for loop-file backends (btrfs / zfs creating an image) |

### Why `btrfs` loop file on `/home` as the project default?

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

## Inspecting (host-level)

```sh
incus list                                  # all VMs across all face roles
incus list --columns ns,disk_usage          # disk per VM
incus image list                            # cached images
incus storage list                          # pools + backend
incus storage info default                  # default pool's real usage
sudo du -sh /var/lib/incus/*                # raw breakdown (CAUTION: undercounts for loop-file backends)
```

## Cleanup (host-level)

| What | Command |
|---|---|
| One cached image | `incus image delete <fingerprint>` |
| All unused images | wait 10 days OR lower `images.remote_cache_expiry` in preseed |
| Nuke everything | `sudo systemctl stop incus && sudo rm -rf /var/lib/incus/* && sudo systemctl start incus` |

For deleting a specific VM, use the face role's `rma` subcommand: `v-<agent> rma` (agents) or `v-<name> rma` (workstations).

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

`<pool>` below = `/var/lib/incus/storage-pools/default/` - the **mount point** where Incus exposes the `default` pool, regardless of backend. For `dir` backend that's also where the actual files live; for loop-file backends, that mount points INTO the loop file's filesystem.

| | **`btrfs` loop on `/home`**<br>(project default) | **`dir` on `/`**<br>(Incus's built-in default) | **`dir` on `/data`** | **`zfs` loop on `/home`** |
|---|---|---|---|---|
| `defaults/main.yml` config | `driver: btrfs`<br>`source: /home/incus-storage.img`<br>`size: 500GiB` | `driver: dir`<br>`source: ""`<br>`size: ""` | `driver: dir`<br>`source: /data/vm/incus`<br>`size: ""` | `driver: zfs`<br>`source: /home/incus-storage.zfs`<br>`size: 500GiB` |
| Pool blocks physically live in | `/home/incus-storage.img` (sparse loop file, btrfs FS inside) | inside `/` filesystem, at `<pool>/` directly | inside `/data` filesystem, at `/data/vm/incus/` directly | `/home/incus-storage.zfs` (sparse loop file, ZFS pool inside) |
| Per-VM root disk | btrfs subvol, CoW-cloned from pool template | full qcow2 file at `<pool>/virtual-machines/<vm>/root.img` | full qcow2 at `/data/vm/incus/virtual-machines/<vm>/root.img` | ZFS dataset, CoW clone of pool template |
| Per-VM snapshot | btrfs subvol snapshot - instant, ~0 space | full dir copy at `<pool>/virtual-machines-snapshots/<vm>/<snap>/` - slow, doubles disk | full dir copy at `/data/vm/incus/virtual-machines-snapshots/<vm>/<snap>/` | ZFS snapshot - instant, ~0 space |
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

- **Whole tree** (cached images + pool + DB + config): symlink `/var/lib/incus` elsewhere - see [Move everything](#move-everything-image-cache--pool--db).
- **Per-pool blocks** (where the VMs / snapshots / pool template actually live): `incus_storage_pool_{driver,source,size}` at first init (see [Configuring the storage pool](#configuring-the-storage-pool)), or `incus storage create <pool> <driver> source=... [size=...]` post-init.
- **Cached-image directory**: not movable separately - it always lives under wherever `/var/lib/incus/` points.

### ext4, btrfs noCoW, or btrfs - which for VM disks?

Depends on the incus storage backend:

| Backend | Best FS | Why |
|---|---|---|
| `dir` | ext4 / xfs | predictable, no double-CoW |
| `dir` | btrfs + `chattr +C` on the storage dir | disables CoW per-file |
| `btrfs` (this project's default, via loop file) | btrfs | incus uses subvolumes + reflinks, manages CoW at the right level. Loop file on ext4 `/home` works because the btrfs layer only sees its own block device |
| `zfs` | zfs | same idea on zvol |

Bad combo: `dir` backend on plain btrfs (no `chattr +C`). qcow2 random writes amplify under btrfs CoW; `du` balloons; fragmentation hurts I/O. The role's `tasks/main.yml` warns about this; the [openSUSE + snapper trap](#opensuse--snapper-trap-btrfs-backend-only) section covers a related failure mode.

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
