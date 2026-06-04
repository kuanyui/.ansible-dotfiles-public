# incus VM hardware/launch-config: what works, what doesn't, why

Why some `hw.*` / `net.*` schema fields are implemented in `ivm` and others are
refused. All rows verified against the incus docs / source (links at bottom),
not assumed. Keep this in sync when incus gains/loses a capability.

## Feature matrix

| Field | incus reality | `ivm` does | Source |
| --- | --- | --- | --- |
| `hw.cpu` / `hw.memory` / `hw.disk` | `limits.cpu`, `limits.memory`, root `--device root,size=` | sets them at `incus create` | instance options |
| `hw.secureboot=false` | `security.secureboot` (bool, default **true**) | `--config security.secureboot=false` (only when disabling) | instance options |
| `hw.tpm` | `tpm` device type; **no VM hotplug** (containers only) | adds `vtpm tpm` to the **stopped** VM, before `incus start` | devices_tpm |
| `net.mode: macvlan` | `nic` device, `nictype=macvlan parent=<host-NIC>` | `device add eth0 nic nictype=macvlan parent=...` | devices_nic |
| `net.mode: bridge` | `nic` device, `nictype=bridged parent=<host-bridge>` | `device add eth0 nic nictype=bridged parent=...` | devices_nic |
| `mounts[]` | `disk` device (virtio-fs); **hotplug OK** for VMs | `device add ... disk source=.. path=..` | devices_disk |
| `mounts[].shadow` | (no native "mask") | overlay an empty read-only dir on each subpath | - |
| `hw.nested_virt` | **works, host-gated, NO per-VM key** | warns if host kernel nesting looks off; no incus config | forum / blog |
| `hw.gpu.mode: virtio` | **NOT possible** (see below) | refused at schema (field removed) | devices_gpu, incus-os#944 |
| `hw.gpu.mode: passthrough` | possible but needs PCI addr + host VFIO | refused at schema (field removed; out of scope) | devices_gpu |

## Why create-then-start (not `incus launch`)

The TPM device has **no hotplug for VMs**. So `ivm init` does `incus create`
(stopped) -> attach all devices -> `incus start`, instead of `incus launch`
(create+start in one). disk devices DO hotplug, but adding everything before
first boot is the one flow that works for hotplug and non-hotplug devices alike.

## nested_virt: supported, but host-gated

incus VMs expose the **host CPU** (vmx/svm), so nested KVM runs inside an incus
VM with **no per-VM incus setting**. The only requirement is on the HOST kernel:
`kvm_intel nested=1` / `kvm_amd nested=1` (modprobe). `ivm` cannot change a host
modprobe setting, so for `hw.nested_virt: true` it just **warns** if the host
looks disabled. (My first read of the docs wrongly said "incus has no nested
support" - corrected here.)

## GPU: incus vs virt-manager

incus's GPU story is **passthrough-only**. The `gputype` device option is exactly
`physical` / `mdev` / `mig` / `sriov` - all hand a real (or sliced) host GPU to
the guest. There is **no virtio-gpu / virgl / venus** (shared software-virtual 3D)
option. Worse, incus's bundled QEMU is **built without virgl**, so even a
`raw.qemu` hack can't add it.

| Use case | virt-manager / libvirt | incus |
| --- | --- | --- |
| Whole-GPU passthrough (VFIO) | yes (`<hostdev>`) | yes (`gputype=physical`) |
| vGPU slice (GVT-g / SR-IOV) | yes (mdev) | yes (`gputype=mdev` / `sriov`) |
| **virtio-gpu + virgl 3D (shared, no passthrough)** | **yes** (`<model type='virtio'>` + `<gl enable='yes'/>`) | **no** (not a device type; QEMU built without virgl) |

### GPU slicing (mdev / SR-IOV / MIG) - the `gputype` non-`physical` options

"Slicing" = split ONE physical GPU into multiple independent virtual GPUs, each
given to a different guest with REAL hardware acceleration. It sits between
`physical` passthrough (whole card -> one guest, exclusive) and virtio-gpu
(software-virtual). When you want several VMs to each have real GPU accel off one
card (VDI, multi-tenant ML, labs) without one card per VM. The three mechanisms
and when they actually work (verified):

| Mechanism | Hardware required | Reality |
| --- | --- | --- |
| `mdev` - Intel GVT-g | Intel iGPU **5th-10th gen** (Broadwell-Comet Lake) | **dead**: not on 11th gen+ |
| `sriov` - Intel Xe | Intel **Iris Xe (11th gen+)** iGPU | GVT-g's modern replacement; consumer-usable with kernel/driver support |
| `mdev`/`sriov` - NVIDIA vGPU | datacenter cards (Tesla/A/L) + **paid licence** + host driver | consumer GeForce officially blocked |
| `mig` - NVIDIA MIG | datacenter Ampere+ (A100/H100) | incus: **containers only** |
| `sriov` - AMD | mostly datacenter (Instinct/MI) | - |

For `ivm`: even where the hardware supports slicing (e.g. Intel Xe SR-IOV),
enabling the virtual functions is HOST-side setup (driver, sysfs, licence) that
`ivm` does not manage - same reason `physical` passthrough is out of scope.

### Intel client iGPU SR-IOV is still NOT turnkey upstream (as of 2026, kernel 6.14)

Surprising but verified: SR-IOV for Intel **client** iGPUs (Alder/Raptor Lake,
Gen12/13) is **not enabled by default in mainline Linux**. The plumbing is in
i915/xe, but Intel has never "flipped the switch" for client parts - it has sat
in "inbound" limbo for years. Upstream SR-IOV is complete only for **datacenter**
GPUs (Flex/Max, via the `xe` driver); Intel upstreamed the product line, not the
client iGPU.

So client iGPU SR-IOV needs the community **`strongtz/i915-sriov-dkms`** (a
snapshot of i915/xe from `intel/mainline-tracking` with the SR-IOV bits ported),
giving up to **7 VFs**, plus host kernel params (`intel_iommu=on`,
`i915.enable_guc=3`, `i915.max_vfs=7`) and BIOS VT-d. Extra friction: the i915 ->
xe driver transition (early `xe` lacked MTL/LNL SR-IOV -> use i915; newer DKMS on
recent kernels uses `xe` to bring up the PF). Net: a host-side, out-of-tree,
hand-built setup - firmly outside what `ivm` automates.

### Consequence for `ivm`

It is **not** the tool for GPU-accelerated VMs.
- Need a desktop? `sys.gui: true` + `ivm gui` gives a SPICE console (software
  rendering) - fine for a browser / light DE, no 3D accel.
- Need real GPU 3D? Use virt-manager, or add `gputype=physical` passthrough to
  `ivm` later (requires new schema fields for the PCI address + host VFIO/IOMMU
  setup, which `ivm` does not manage).

## Sources

- Instance options (security.secureboot, limits.*): https://linuxcontainers.org/incus/docs/main/reference/instance_options/
- GPU device (gputype list): https://linuxcontainers.org/incus/docs/main/reference/devices_gpu/
- TPM device (no VM hotplug): https://linuxcontainers.org/incus/docs/main/reference/devices_tpm/
- NIC device (nictype macvlan/bridged): https://linuxcontainers.org/incus/docs/main/reference/devices_nic/
- Disk device (VM hotplug, virtiofs): https://linuxcontainers.org/incus/docs/main/reference/devices_disk/
- incus QEMU lacks virgl: https://github.com/lxc/incus-os/issues/944
- Nested virt on incus (host-gated): https://discuss.linuxcontainers.org/t/how-to-run-an-incus-vm-inside-an-incus-vm-nested-virtualization/19499 ; https://blog.simos.info/how-to-run-an-incus-vm-inside-an-incus-vm-nested-virtualization/
- Intel client iGPU SR-IOV (DKMS, not mainline-default; up to 7 VFs; Raptor Lake): https://github.com/strongtz/i915-sriov-dkms ; https://forum.proxmox.com/threads/intel-igpu-sr-iov-help-on-raptor-lake-i9-13900h.180420/
- Intel GVT-g generations (Broadwell-Comet Lake; gone on 11th gen+): https://wiki.archlinux.org/title/Intel_GVT-g
