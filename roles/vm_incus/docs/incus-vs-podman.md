# incus containers vs podman containers - why this project uses both

Why `roles/vm_incus` (the `ivm` launcher) uses **incus VMs**, `roles/vm_podman`
(the `pvm` launcher) uses **podman**, and neither should switch to "incus
containers". Not a feature-count comparison - the two solve **different shapes**
of problem.

## System containers vs application containers

| | incus container (LXC) | podman container (OCI) |
| --- | --- | --- |
| Nature | **System container**: full systemd + an OS userland, like a "lightweight VM sharing the host kernel". Persistent; you exec/ssh in and treat it as a box. | **Application container**: run one image's workload, then discard. |
| Image ecosystem | own image server (distro rootfs). incus 6.x (2024) added OCI app-container support, but it's secondary. | **native OCI**: Docker Hub, Dockerfile, compose - the mature ecosystem. |
| Model | persistent / pet | ephemeral / cattle, rootless-first |
| Extra isolation | LXC + seccomp | optional **libkrun** (microVM - an extra VM boundary) |

incus is **not "less capable"** than podman: it adds things podman has no concept
of (system containers AND VMs under one API/CLI, live migration, snapshots,
clustering). But for **"run an OCI app, rootless, ephemeral, throwaway"**, podman
is the right tool (native OCI, the registry/Dockerfile ecosystem, libkrun).

## Consequence for this repo

- **`roles/vm_podman` (`pvm`) stays podman.** It runs ephemeral, rootless OCI
  containers (dev / agent boxes), with libkrun available for an extra isolation
  boundary - exactly podman's sweet spot. Switching to incus containers would lose
  the OCI ecosystem + libkrun model and gain nothing for that use case.
- **`roles/vm_incus` (`ivm`) uses incus VMs.** Stronger isolation than a shared
  kernel (separate kernel, standalone `virtiofsd` + `pivot_root` + seccomp) -
  wanted for agents touching source while credentials sit on the host.
- **No separate "incus container" role.** If a lighter-than-VM incus *system
  container* ever becomes useful, it would be a new `ivm` template option
  (e.g. `os.type: container`), still inside `roles/vm_incus` - "one launcher, many
  templates", not a new role. This is why `vm_incus` is the *only* incus consumer
  and the former `_incus_*` helper roles were folded into it.
