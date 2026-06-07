# Incus host setup (storage pool, network, troubleshooting)

Host-level incus daemon setup for `roles/incus_vm`, run via `tasks/incus_host_install.yml` (folded in from the former `_incus_host_setup` role once `incus_vm` became the sole consumer). Gated on `not incus_vm_skip_host_setup`. Reversed by `tasks/incus_host_uninstall.yml` on `incus_vm_state: absent` (see [Uninstall / teardown](#uninstall--teardown)).

Covers the host-level concerns - independent of any specific VM template: supported distros, what gets installed on the host, the `default` storage pool config matrix, the openSUSE+snapper btrfs trap, moving incus data around post-install, host-level inspecting / cleanup, and the network / virt-manager FAQs. For the launcher itself (templates, `ivm` subcommands), see [`roles/incus_vm/README.md`](../README.md).

## What this does on the host

- Asserts host distribution is one of: Fedora 43+ / Debian trixie+ (or bookworm-backports) / openSUSE Tumbleweed / openSUSE Leap 15.6+ (those are the distros that ship `incus` in their official repo). Escape hatch: `incus_vm_skip_host_setup: true`.
- Installs `incus` package + `guestfs-tools` (provides `virt-builder` for GPG-verified VM disk image fetch).
- Probes `incus.service`; starts + enables if not active.
- Ensures `incus-user.socket` is enabled + started (provides the lower-privilege `/run/incus/unix.socket.user` owned by group `incus`; Fedora / openSUSE ship it disabled by default - upstream-acknowledged packaging gap).
- Adds `$USER` to the `incus` group (lower-privilege; the `incus` CLI auto-detects the user socket via `if !PathIsWritable(adminSocket) && PathIsWritable(userSocket) { ... }` in `client/connection.go`, and routes operations into a per-user project named `user-<UID>` for isolation). Removes legacy `incus-admin` membership from prior role versions (root-equivalent, no longer needed). Re-login (or `newgrp incus`) required for the new group to be active in any existing shell; the role hard-aborts on first-time add so this can't be missed silently.
- Probes `/` filesystem type; warns about the `qcow2 + btrfs CoW` trap when defaulting to `dir` backend on a btrfs `/`.
- Runs `incus admin init --preseed` exactly once (only if the `default` storage pool doesn't already exist).
- On firewalld hosts (Fedora / openSUSE): moves the `incusbr0` bridge into the `trusted` zone (only if not already there). Without this, the default `public` zone DROPs DHCP and VMs never get an IPv4 lease - see [Q&A](#firewalld-hosts-vms-get-an-ipv6-address-but-no-ipv4-apt-fails-with-temporary-failure-resolving). Skipped on non-firewalld hosts (Debian + bare nftables).

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

This does NOT auto-snapshot. `ivm` exposes snapshots via `ivm snapshot create|list|restore|delete`. Cost depends purely on backend:

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

> [!NOTE]
> This project's default uses btrfs LOOP FILE on `/home` (not a btrfs subvolume of `/`), so the snapper trap doesn't apply to the default config - snapper doesn't snapshot `/home`'s loop file contents because they're inside a single file from snapper's perspective.

## Configuring the storage pool

Three vars in [`defaults/main/incus_host_install.yml`](../defaults/main/incus_host_install.yml) drive the preseed pool config. Set in `host_vars/<hostname>.yml`. Effective ONLY at first-time `incus admin init --preseed`:

| Var | Project default | Meaning |
|---|---|---|
| `incus_storage_pool_driver` | `btrfs` | backend: `dir` / `btrfs` / `zfs` / `lvm-thin` |
| `incus_storage_pool_source` | `/home/incus-storage.img` | meaning depends on the driver; see [Source semantics per driver](#source-semantics-per-driver) below |
| `incus_storage_pool_size` | `500GiB` | only for `source:` forms where Incus CREATES a sparse file (loop file). For everything else (dir tree, existing subvolume, dedicated block device, already-existing ZFS dataset / LVM thin pool), leave empty |

### Source semantics per driver

This is the key section, and where the project originally got it wrong. **incus only CREATES a loop file at its own fixed path `/var/lib/incus/disks/<pool>.img` (on `/`), and only when `source:` is EMPTY.** A custom file path is NOT "make a loop file here". (Verified in the incus source: `driver_btrfs.go` / `driver_zfs.go`, `Create()`.)

| `driver:` | `source:` | What incus does |
|---|---|---|
| `btrfs` / `zfs` / `lvm` | **empty** (+ `size:`) | **The only incus-made loop file:** sparse `.img` at `/var/lib/incus/disks/<pool>.img` **on `/`** (btrfs FS / file-vdev zpool / LVM PV inside). For a big `/home`, relocate `/var/lib/incus` first → [Move everything](#move-everything-image-cache--pool--db). |
| `dir` | empty, or a dir path | VM disks in `/var/lib/incus/storage-pools/default/` (on `/`), or in that dir. |
| `btrfs` | existing **btrfs subvolume** path | Uses it (CoW from that FS). No `size:`. |
| `zfs` | existing **dataset** name (`tank/incus`, no leading `/`) | Uses it. No `size:`. |
| `lvm` | existing **VG / thin-pool** name | Uses it. |
| `btrfs` / `zfs` | a **block device** (`/dev/...`) | `mkfs.btrfs` / `zpool create` on it. No `size:`. |
| `btrfs` | ⚠️ a **plain file path** (`/home/x.img`) | **NOT a loop file** → incus runs `btrfs subvolume create <path>` → FAILS (`Inappropriate ioctl`) unless that path is already on btrfs. |
| `zfs` | ⚠️ a plain file path | **Rejected** at validation. |

So CoW storage on a big `/home` needs ONE of: **(a)** relocate `/var/lib/incus` to `/home`, then empty `source:`; **(b)** `source:` = an existing btrfs subvolume / zfs dataset / block device you set up on `/home`; **(c)** `dir` driver (no CoW). There is **no** "make a loop file at `/home/x.img`" form - that was the bug behind the `Inappropriate ioctl` failure.

### Why `btrfs` loop file on `/home` as the project default?

The project targets hosts where `/` is a small btrfs system partition (often ~160-180 GB on openSUSE / Tumbleweed installs) and `/home` is a much larger ext4 partition. Out of the three btrfs source forms above:

- Existing btrfs subvolume on `/`: `/` is too small to hold VM disks.
- Block device dedicated to Incus: requires repartitioning `/home` or adding a new disk - hardware-level change we don't want to assume.
- Loop file on `/home`: works on the existing ext4 `/home` partition without touching anything. Sparse file, ~0 initial space.

So loop file is the project's default because it requires zero hardware / partition changes. Tradeoff vs a dedicated block device: ~5-10% I/O overhead (ext4 → loop driver → btrfs), measurable but acceptable for the assumed use case.

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

**Dedicated block device** (best performance, CoW; requires you've partitioned `/dev/nvme0n1p3` or similar for this purpose):

```yaml
incus_storage_pool_driver: btrfs
incus_storage_pool_source: /dev/nvme0n1p3
incus_storage_pool_size: ""
```

**Existing btrfs subvolume** (CoW, no loop file overhead; requires you have a btrfs FS somewhere with enough space):

```yaml
incus_storage_pool_driver: btrfs
incus_storage_pool_source: /mnt/btrfs-data/incus
incus_storage_pool_size: ""
```

**Already-set-up ZFS dataset** (CoW, no loop file overhead; requires host has ZFS):

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
incus list                                  # all VMs
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

For deleting a specific VM, use `ivm delete` (from the VM's dir) or `incus delete <vm-name>`.

## Uninstall / teardown

`incus_vm_state: absent` always removes the user-space `ivm` tool (`tasks/ivm_uninstall.yml`). The host-level incus layer is reversed by `tasks/incus_host_uninstall.yml`, but **every step is OFF by default** - you opt into each with an `incus_vm_uninstall_*` toggle (defined in [`defaults/main/incus_host_uninstall.yml`](../defaults/main/incus_host_uninstall.yml)). The distro `incus` / `guestfs-tools` **packages are never removed**.

| Toggle (`incus_vm_uninstall_*`) | Reverses | Risk |
|---|---|---|
| `remove_user_from_incus_group` | the `incus` group add | reversible (re-login) |
| `revert_firewalld_incusbr0_zone` | `incusbr0` trusted-zone | host-local, low |
| `disable_incus_daemon_and_socket` | `incus.service` + `incus-user.socket` enable | shared: stops incus host-wide |
| `delete_all_instances` | - | **destroys all VM disks** |
| `delete_autocreated_user_projects` | incus-user's `user-*` projects + `incusbr-*` bridges | deletes those projects' VMs |
| `delete_incusbr0_network` | preseed's `incusbr0` bridge | network only, no data |
| `delete_default_storage_pool` | preseed's `default` pool | **erases pool**; needs instances + user-* projects gone first |

Storage (`delete_default_storage_pool`) and network (`delete_incusbr0_network`) are split on purpose - they are orthogonal.

Convenience targets:
- `make incus-uninstall-ivm` - safe; removes only `ivm` (no toggles, no sudo).
- `make incus-teardown-host` - DESTRUCTIVE; every toggle EXCEPT group removal (deletes all VMs + pool + bridges, disables the daemon; keeps packages + your `incus` group, so no re-login). Customize via the `INCUS_VM_HOST_TEARDOWN_FLAGS` Makefile var (e.g. append `-e incus_vm_uninstall_remove_user_from_incus_group=true`).

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

> [!TIP]
> **What is a "loop file"?** A regular file (e.g. `/home/incus-storage.img`) that sits on an ordinary host filesystem (e.g. ext4 `/home`), but the Linux kernel can be told to treat the file's bytes as if they were a raw block device via the **loop driver** (`/dev/loop<N>`). Incus then formats a different filesystem (a btrfs filesystem, or a ZFS pool) INSIDE those bytes, and mounts / imports that inner filesystem at a canonical path under `/var/lib/incus/`. So from above (`ls /var/lib/incus/storage-pools/default/`) you see the inner filesystem's contents like any directory; from below (`du -sh /home/incus-storage.img`) you see how many bytes the file actually consumes on ext4 `/home`. The whole point is to get btrfs / ZFS semantics (snapshots, CoW clones) without needing a dedicated btrfs / ZFS partition.

Two backend families behave differently on disk:

- **`dir` backend**: the `source:` value IS the storage directory tree on a real filesystem - no loop file involved. Incus writes VM disks (qcow2 files), snapshots (directory copies), and custom volumes (ISOs etc.) directly into that directory. With empty `source:` it defaults to `/var/lib/incus/storage-pools/default/`. There is no separate "mount point"; the `source:` path IS the path you `ls`.
- **`btrfs` / `zfs` loop-file backend**: the `source:` value is the path to a sparse `.img` file (a loop file as defined above). The inner filesystem (btrfs FS or ZFS pool) lives inside that file. Incus mounts the loop file's btrfs FS at `/var/lib/incus/storage-pools/default/` (or imports the inner ZFS pool with the name `default`) at daemon start, so `ls` and `incus storage info` work via that path even though the actual blocks are inside the `.img` file.

Placeholders used in the cells below:

- `<vm-name>` - the VM's name. `ivm` names it `ivm-<template>-<cwd-path>` by default (e.g. `ivm-claude-...`), or whatever you pass to `ivm init <template> <name>`.
- `<image-fingerprint>` - the SHA256 fingerprint of a cached incus image, ~64 hex chars; for `images:debian/13` it's something like `b8a3e07c1f29...` (the daemon-level cache directory `/var/lib/incus/images/<image-fingerprint>/` stores the corresponding tarball + metadata).
- `<snap>` - whatever name you passed to `incus snapshot create <vm-name> <snap>`.
- `<volname>` - the volume name you passed to `incus storage volume import default <iso-file> <volname> --type=iso`.

| | **btrfs loop file on `/home`**<br>(project default) | **`dir` backend on `/`**<br>(Incus built-in default) | **`dir` backend on `/data`** | **zfs loop file on `/home`** |
|---|---|---|---|---|
| `incus_host_install.yml` config | `driver: btrfs`<br>`source: /home/incus-storage.img`<br>`size: 500GiB` | `driver: dir`<br>`source: ""`<br>`size: ""` | `driver: dir`<br>`source: /data/vm/incus`<br>`size: ""` | `driver: zfs`<br>`source: /home/incus-storage.zfs`<br>`size: 500GiB` |
| Where the actual blocks live on host | `/home/incus-storage.img` (a sparse btrfs loop file) | `/var/lib/incus/storage-pools/default/` (a real directory tree) | `/data/vm/incus/` (a real directory tree) | `/home/incus-storage.zfs` (a sparse ZFS loop file) |
| Where you `ls` to navigate the pool | `/var/lib/incus/storage-pools/default/` (Incus mounts the loop file's btrfs FS here at daemon start) | `/var/lib/incus/storage-pools/default/` (= the storage path itself) | `/data/vm/incus/` (= the storage path itself) | `/var/lib/incus/storage-pools/default/` (Incus imports the ZFS pool as `default` and exposes it here at daemon start) |
| Per-VM root disk | btrfs subvolume at `/var/lib/incus/storage-pools/default/virtual-machines/<vm-name>/`, CoW-cloned from the pool template. Backing blocks live inside `/home/incus-storage.img` | qcow2 file at `/var/lib/incus/storage-pools/default/virtual-machines/<vm-name>/root.img`, sparse, full copy of the cached image | qcow2 file at `/data/vm/incus/virtual-machines/<vm-name>/root.img`, sparse, full copy of the cached image | ZFS dataset named `default/virtual-machines/<vm-name>`, CoW clone of the pool template. Backing blocks live inside `/home/incus-storage.zfs` |
| Per-VM snapshot | btrfs subvolume snapshot at `/var/lib/incus/storage-pools/default/virtual-machines-snapshots/<vm-name>/<snap>/` (instant, ~0 space until the source diverges) | full directory copy at `/var/lib/incus/storage-pools/default/virtual-machines-snapshots/<vm-name>/<snap>/` (slow, ~doubles the VM's disk usage) | full directory copy at `/data/vm/incus/virtual-machines-snapshots/<vm-name>/<snap>/` (slow, ~doubles the VM's disk usage) | ZFS snapshot named `default/virtual-machines/<vm-name>@<snap>` (instant, ~0 space until the source diverges) |
| Pool template (image clone source) | btrfs subvolume at `/var/lib/incus/storage-pools/default/images/<image-fingerprint>/`; CoW source for per-VM root disks. Backing blocks live inside `/home/incus-storage.img` | none - `dir` has no pool template. Each VM is a fresh full copy of the daemon-level cached image (`/var/lib/incus/images/<image-fingerprint>/`) | none - same as `dir` on `/` | ZFS dataset named `default/images/<image-fingerprint>`; CoW source for per-VM root disks. Backing blocks live inside `/home/incus-storage.zfs` |
| Imported ISO (custom volume) | btrfs subvolume at `/var/lib/incus/storage-pools/default/custom/iso/<volname>/`. Backing blocks live inside `/home/incus-storage.img` | regular directory at `/var/lib/incus/storage-pools/default/custom/iso/<volname>/` (the ISO file is inside that directory) | regular directory at `/data/vm/incus/custom/iso/<volname>/` (the ISO file is inside that directory) | ZFS dataset named `default/custom/iso/<volname>`. Backing blocks live inside `/home/incus-storage.zfs` |
| CoW snapshots cheap? | **yes** (btrfs reflinks) | no (full copy each time) | no (full copy each time) | **yes** (ZFS snapshots) |

#### Reading the table

- The row **"Where the actual blocks live on host"** is what `du` / `df` measure. For the two loop-file backends (btrfs loop file on `/home`, zfs loop file on `/home`), `du -sh /var/lib/incus/` **UNDERCOUNTS** the pool because the pool's data lives inside the `.img` file on `/home`, not under `/var/lib/incus/`. To get real usage:
  - btrfs loop case: `du -sh /home/incus-storage.img` (or `incus storage info default`)
  - zfs loop case: `du -sh /home/incus-storage.zfs`
- For the two `dir` cases, the "actual blocks" row equals the "navigate the pool" row, so `du` on either path counts everything.
- For `dir` on `/data`, the directory `/var/lib/incus/storage-pools/default/` **does not exist at all** - the pool is just `/data/vm/incus/`. The "mount point" canonicalization at `/var/lib/incus/storage-pools/default/` only happens for the loop-file backends, which need a place to mount the inner filesystem.

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

### firewalld hosts: VMs get an IPv6 address but no IPv4, apt fails with "Temporary failure resolving"

Symptom: VM has only an `fd42:...` (IPv6 SLAAC) address, `ip -4 addr` shows nothing, `ping 1.1.1.1` is "Network is unreachable".

Cause: firewalld leaves `incusbr0` unassigned, so it falls into the default `public` zone. `public` permits ICMPv6 (so IPv6 RA gets through and SLAAC works) but DROPs DHCP (udp/67) on INPUT - so the VM's DHCPv4 DISCOVER never reaches the bridge's dnsmasq, and no IPv4 lease is issued. NAT / forwarding being fine is irrelevant when the VM has no IPv4 at all.

Fix (this role now does it automatically; manual form for already-provisioned hosts):

```sh
sudo firewall-cmd --permanent --zone=trusted --change-interface=incusbr0
sudo firewall-cmd --reload
incus restart <vm>            # re-trigger DHCP
incus exec <vm> -- ip -4 addr show    # expect 10.x.x.x
```

`trusted` scope is one interface only - a private internal NAT segment carrying only your own VMs - so it does NOT widen your real NICs (still in `public`). On openSUSE this is the same firewalld that YaST Firewall manages; `incusbr0` won't appear in YaST's interface picker (it's not NetworkManager-managed), but YaST sees the binding after the CLI writes it.

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

### Clipboard: copying in a VM shell lands in my host clipboard, but pasting into a TUI (Claude Code etc.) fails - what's going on?

`incus exec` (the text shell behind `ivm shell`) is just a byte pipe - it has **no** text-shell clipboard feature. What you see is the **terminal emulator** (Konsole / etc.), not incus.

| Direction | Mechanism | Who does it |
| --- | --- | --- |
| Copy (VM app -> host clipboard) | App (e.g. Claude Code) emits an **OSC 52** escape (`\e]52;...`); the terminal decodes it and writes the host clipboard (KDE Klipper then shows it) | terminal emulator |
| Paste (host clipboard -> VM app) | keyboard paste; the terminal sends the bytes down the PTY | terminal emulator |

Same behavior over ssh / `tmux` (with `set-clipboard on`) / podman - it is terminal-level, not runtime-level. incus only carries the bytes.

**Why paste into a full-screen TUI fails:** Claude Code (and `htop`, `vim` with `mouse=a`, ...) turns on xterm **mouse reporting**, so the terminal forwards mouse clicks to the app and its own right-click "Paste" menu stops appearing. Paste with the keyboard instead:

- `Shift+Insert` or `Ctrl+Shift+V` - pastes the **clipboard** (Ctrl+C / Klipper / where OSC 52 writes)
- `Shift`+middle-click - pastes the **primary selection** (the last mouse-highlighted text), a *different* buffer from the clipboard
- hold `Shift` and right-click - Konsole bypasses mouse reporting while Shift is held, so the local "Paste" menu returns

(Primary selection vs clipboard are two separate buffers; if a paste gives stale/wrong text, you grabbed the wrong one - `Shift+Insert` for clipboard, `Shift`+middle-click for the last mouse selection.)

**GUI path is different:** `ivm gui` (`incus console --type=vga` + SPICE) gets real host<->guest clipboard sharing from `spice-vdagent` in the guest - that one *is* an agent-level feature, not OSC 52.

**Security note:** OSC 52 lets any program that can write to your terminal **set** your host clipboard (write direction). Reading is usually blocked by the terminal. To disable it entirely, turn OSC 52 off in the terminal emulator (not in incus); the cost is that the VM app's copy no longer reaches the host clipboard.
