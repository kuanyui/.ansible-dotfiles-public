# ivm vs quickemu - different shapes of VM tool

Whether `roles/incus_vm` (the `ivm` launcher) reinvents [quickemu](https://github.com/quickemu-project/quickemu). Short answer: **no** - they sit on different axes and overlap in exactly one cell ("run a Linux VM"). Like [`incus-vs-podman.md`](incus-vs-podman.md), this is **not a feature-count contest**: the two optimise for different shapes of problem. This doc maps positioning + a full feature comparison, and names the ONE place `ivm` would genuinely duplicate quickemu's hard-won work.

> [!NOTE]
> **As-of / method.** quickemu facts below are verified against its source on the
> `master` branch, fetched **2026-06** (`quickemu` 2934 lines + `quickget` 4059
> lines of bash), not from memory. quickemu moves fast - re-check before relying
> on a specific row. `ivm` facts are from this repo's tree (`files/ivm`, the
> schema, the role tasks).

## TL;DR

| | `ivm` (this repo) | quickemu |
| --- | --- | --- |
| Built on | **Incus** (LXD fork) KVM VMs | **QEMU** directly (bash wrapper) |
| One-line thesis | One **reproducible, headless Linux dev VM per project dir**, integrated with this repo | **Run almost any OS desktop, fast and interactively**, on a laptop |
| Definition | Declarative **YAML + JSON Schema** | Per-VM `.conf` (bash, sourced) |
| Guest OS (working) | Linux: Debian/Ubuntu/openSUSE/Fedora | Linux (~1000 editions) **+ Windows + macOS** |
| Killer feature | cwd-bound VM, virtio-fs mount with **secret masking**, host-side provisioning, repo dotfiles/packages | `quickget` auto-download + optimised QEMU for **macOS/Windows**, 3D/USB/audio desktop |
| Host→guest exec | `incus exec` (TTY, no SSH/creds) | SSH (auto port-forward) |
| Implementation | ≈1,540-line typed Python (mypy `--strict`) | ≈7,000 lines bash (2 monolithic scripts) |

**Verdict:** not reinventing the wheel. quickemu's core value (macOS/Windows + any-distro desktop, interactive GUI, 3D/USB/audio) is precisely what `ivm` does **not** do and does not aim to. `ivm`'s core value (per-project headless dev VM, cwd mount + secret masking, repo integration, no-SSH exec) is precisely what quickemu has **no concept of**. The only real duplication risk is the **unimplemented Windows tier** (see [below](#the-overlap-and-the-one-reinventing-the-wheel-risk)).

## The core axis

quickemu answers: *"I want OS X running in a window on my machine, with the least fuss."* X can be macOS Sequoia, Windows 11, or any of ~1000 Linux editions; `quickget` fetches the image, `quickemu` boots it with sane QEMU flags, you use it interactively (SPICE display, 3D, audio, USB).

`ivm` answers: *"Every project dir gets its own throwaway, reproducible, isolated **Linux** box that an agent can work in, sharing my cwd but **not** my secrets, provisioned the same way as the rest of this repo."* No GUI assumption, no macOS/Windows, no manual image hunting - the template + cwd binding + host-side provisioning are the point.

Different axes -> they barely compete.

## Feature comparison

### Guest OS + image acquisition

| | `ivm` | quickemu | Note |
| --- | --- | --- | --- |
| Linux distros | Debian, Ubuntu, openSUSE, Fedora | ~1000 editions across most distros | `ivm` resolves package manager + `ansible_os_family` per distro |
| Windows | schema-defined, **not implemented** (`init` errors) | **yes**, mature (10/11/Server, TPM 2.0, virtio drivers, unattended) | see risk section |
| macOS | **no** | **yes** (Sequoia -> Mojave, recovery-image download) | quickemu-only |
| BSD / Haiku / ReactOS / ... | no | yes | quickemu-only |
| How images arrive | incus image remotes (`images:debian/13`), or `iso`/`virt-builder` (planned) | `quickget` auto-downloads ISO/recovery + writes the `.conf` | quickemu's `quickget` is a big reason it exists |

### Definition + provisioning

| | `ivm` | quickemu |
| --- | --- | --- |
| Config format | YAML, validated by JSON Schema (editor LSP shows inline docs) | `.conf` key=value, sourced as bash |
| Provisioning | **host-side** via `incus exec`: baseline + `distro_package_groups` (shared with `roles/distro_packages`) + timezone + `user` + zsh + sshd + `post_install_script`; pushes repo dotfiles | none built-in; you script cloud-init / configure inside the guest |
| Repo integration | reuses this repo's package groups + dotfiles staging | standalone, no opinion |
| Reproducibility | template re-runs identically | `.conf` reproduces the VM shell, not the guest's inside state |

### Host -> guest command execution

| | `ivm` | quickemu |
| --- | --- | --- |
| Primary path | `incus exec` - **TTY, no SSH, no credentials, works even if guest networking is down** (`ivm shell` = `incus exec zsh`) | **SSH**, auto port-forward (`hostfwd=tcp::<22220-22228>-:22`) |
| Agent channel | incus agent (built in) | QEMU Guest Agent socket present (`org.qemu.guest_agent.0`), but **no `exec` wrapper command** - you'd hand-write QMP `guest-exec` JSON |
| Optional SSH | yes (`sys.ssh_server.*`) | yes (the primary path) |

This is the sharpest day-to-day difference: `ivm` gets ergonomic host->guest exec for free from incus; quickemu sends you to SSH (or to hand-rolling the guest-agent protocol).

### Storage, CoW, snapshots

| | `ivm` | quickemu |
| --- | --- | --- |
| Disk | incus storage pool; **default = btrfs loop file on `/home`** (chosen for cheap CoW) | standalone `qcow2` per VM (`qemu-img create`, no backing file) |
| CoW layer | **storage backend** (btrfs/zfs/lvm-thin) | qcow2 format itself |
| Snapshots | **whole-instance**, first-class (`ivm snapshot create/list/restore/delete`); instant + space-efficient on a CoW pool | qcow2 **internal** snapshots (`qemu-img snapshot -c/-a/-d`), per-disk, in-file; ergonomics rough (the `qqX` project exists to fix this) |
| Clone-from-image | yes - `incus create` from an image shares blocks via CoW (fast, thin) | **no** linked-clone / instant-provision; each VM is a fresh standalone image |
| btrfs double-CoW trap | role **warns** + recommends `chattr +C` / dedicated pool ([host-setup doc](incus-host-setup.md)) | sets `nocow=on` on the qcow2 file (host-FS flag; does **not** disable qcow2's own CoW) |

Both grapple with the same qcow2-on-btrfs double-CoW pitfall - different fixes. The capability gap is **clone-from-image + instant whole-instance snapshots**, which incus has and quickemu does not.

### Networking

| | `ivm` | quickemu |
| --- | --- | --- |
| Default | NAT (incus bridge), zero host setup | user-mode NAT + SSH/port forwarding |
| LAN-visible | `macvlan` / `bridge` (needs `net.parent`) | bridged options |
| Forwarding | via incus | automatic SSH + arbitrary port forwards |

### Desktop / GPU / passthrough / sharing

quickemu wins this whole category by design - it is a desktop-VM tool; `ivm` deliberately is not (see [`incus-hardware-capabilities.md`](incus-hardware-capabilities.md)).

| | `ivm` | quickemu |
| --- | --- | --- |
| Display | `ivm gui` -> SPICE console, **software rendering only** | full SPICE, multi-monitor |
| 3D accel | **none** (incus QEMU built without virgl; not a device type) | **VirGL** 3D for Linux guests; VirtIO-GPU 2D for Windows |
| GPU passthrough | out of scope (host VFIO/IOMMU not managed) | not in core (separate `quickpassthrough`, WIP) |
| USB / smartcard / webcam | not wired up | **passthrough supported** |
| Audio | not a goal | **full-duplex** |
| Clipboard host<->guest | depends on `spice-vdagent` in guest | **yes** (SPICE) |
| File sharing | virtio-fs mount of cwd (+ secret masking) | virtiofs / 9p / webdav / Samba |

### Lifecycle + commands

`ivm`: `init shell shell-root start stop reboot delete update overwrite-dotfiles set-password unset-password enable-user-sudo disable-user-sudo snapshot gui info list env` - all resolve the target VM by **cwd binding** (`user.ivm_init_at_dir`), so everyday commands take no args. quickemu: `start / stop / kill / snapshot / delete-disk / delete-vm` per `.conf`, plus `quickget`; `quickgui` (Flutter) is a separate GUI frontend.

### Host platform + maturity

| | `ivm` | quickemu |
| --- | --- | --- |
| Host OS | Linux only (needs incus daemon, storage pool, group setup) | **Linux + macOS** |
| Install weight | heavier (daemon + pool + preseed) | light (a script; VMs can live on a USB stick, no root) |
| Portability of a VM | incus instance (host-bound) | a folder of files you can move/copy |
| Maturity | solo-maintained; statically verified (mypy `--strict`, `--dry-run`, `make incus-sandbox`); **no real-incus E2E in CI** | years old, large user base, battle-tested across many OSes; ecosystem (`quickgui`, `qqX`) |
| Codebase | ≈1,540 lines typed Python + JSON Schema | ≈7,000 lines bash, 2 monolithic scripts |

> The language gap (typed Python+schema vs bash) is a red herring. quickemu's real
> value is not its code - it's the **domain knowledge baked in**: which macOS
> recovery image maps to which version, which virtio drivers Windows needs, which
> QEMU flags each OS wants. That know-how is the moat, not the implementation.

## Where `ivm` falls short of quickemu

- **No macOS, no (working) Windows, no BSD/etc.** quickemu runs them all.
- **No 3D / USB / smartcard / webcam / audio**; SPICE console is software-rendered. Not a desktop-replacement tool.
- **No turnkey image catalog.** `quickget`'s ~1000-edition auto-download has no `ivm` equivalent.
- **Linux host only**, heavier install (incus daemon + storage pool). quickemu also runs on macOS hosts and off a USB stick without root.
- **Less battle-tested**: solo project, no real-incus end-to-end CI; quickemu has years and a large user base.
- **Snapshots/clone are incus' strength, but `dir` pools lose CoW.** The CoW advantage only holds on a btrfs/zfs/lvm-thin pool (the role's default is btrfs - confirm yours).

## Where `ivm` does what quickemu can't

- **One VM per project directory.** `ivm init` binds to cwd; subdir commands offer the nearest ancestor's VM. Quickemu has no project model.
- **cwd mounted + secrets masked.** virtio-fs mounts the working dir; `mounts[].shadow` overlays empty read-only dirs on `.git`/`.env`/etc. so an in-VM agent can't read host secrets. No quickemu analog.
- **Host-side provisioning, zero guest Ansible/Python**, reusing this repo's `distro_package_groups` + dotfiles.
- **No-SSH, no-credential exec** with a TTY (`incus exec`), works even with guest networking down.
- **Instant CoW snapshots + clone-from-image** as first-class lifecycle ops (on a CoW pool).
- **One launcher, many templates** - the same tool could later grow an `os.type: container` template ([incus-vs-podman.md](incus-vs-podman.md)).

## The overlap, and the one reinventing-the-wheel risk

The honest overlap is a single cell: **booting a Linux VM**. For that narrow task quickemu is more mature - but you lose every `ivm`-only feature above, so it is not a drop-in replacement for this repo's use case.

The **one** place `ivm` would truly duplicate quickemu is the **Windows tier** (`os.type: windows`, currently schema-defined but `init` errors out). Running Windows (and macOS) under QEMU - TPM/SecureBoot wiring, virtio driver injection, `unattend.xml`, recovery-image fetching - is exactly the multi-year know-how encoded in quickemu's 7000 lines of bash. Re-deriving it inside `ivm` is low return.

**Recommendation:**
- Keep `ivm` focused on its real niche: **per-project headless Linux dev VMs**.
- For a macOS or Windows **desktop**, just run quickemu alongside; don't bolt it onto `ivm`.
- If `ivm` ever truly needs Windows, prefer **deferring to / shelling out to** `quickget`/`quickemu` over reimplementing the QEMU-for-Windows path from scratch.

## When to use which

| Want to... | Use |
| --- | --- |
| Try a distro, run macOS/Windows, interactive desktop, 3D/USB/audio, run off a laptop (incl. macOS host) | **quickemu** |
| Per-project isolated **Linux** dev VM for agents/coding, reproducible from YAML, cwd mounted with secrets masked, integrated with this repo's dotfiles/packages, no-SSH exec, CoW snapshots per project | **`ivm`** |

## Sources

- quickemu source (qcow2 / `qemu-img snapshot` / `hostfwd` 22220-22228 / guest-agent socket / `nocow=on`), `master` @ 2026-06: https://github.com/quickemu-project/quickemu and https://raw.githubusercontent.com/quickemu-project/quickemu/master/quickemu
- quickemu OS support + features (macOS/Windows, VirGL, USB/smartcard, SPICE clipboard, file sharing, Linux+macOS host): https://github.com/quickemu-project/quickemu
- QEMU Guest Agent protocol (`guest-exec`, why it is not ergonomic for ad-hoc commands): https://qemu-project.gitlab.io/qemu/interop/qemu-ga.html
- `qqX` - third-party tool that exists to make quickemu snapshots usable: https://qqxproject.org/Snapshots
- Sibling docs: [`incus-hardware-capabilities.md`](incus-hardware-capabilities.md) (GPU/3D reality), [`incus-host-setup.md`](incus-host-setup.md) (storage pools + CoW backends), [`incus-vs-podman.md`](incus-vs-podman.md) (positioning precedent)
