# roles/podman_oci_runtimes/

Installs an alternative **OCI runtime** for podman (e.g. `libkrun` microVM) + writes
`containers.conf`.

- **Type**: face role - `make apply-podman-oci-runtimes` (playbook `podman_oci_runtimes.yml`)
- **Gate**: `setup_podman_oci_runtimes` (default **false** - nested KVM is rarely wanted
  in a guest; the ONE role that kept its `setup_*` gate)
- **Vars**: `podman_runtime` (`default` | `libkrun`), `podman_runtime_scope` (`user` | `system`)
- **Deploys**: the runtime packages + `containers.conf` (`+LIBKRUN`)
