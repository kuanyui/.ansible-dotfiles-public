"""Sandbox config for `playbooks/incus_vm.yml`.

Verifies the role-level concerns of `roles/incus_vm`: the `ivm` engine binary,
`vm.schema.json`, and the example `vm-templates/` get installed to the right
places, the user/root dotfiles staging is rendered under `vm-rootfs/`, and the
round-trip uninstall removes the binary + the role subdir back to baseline.

What we deliberately DON'T test here: the `ivm` runtime (incus launch / exec /
virtio-fs / apt-in-guest), which needs nested KVM and is orthogonal to the
install path. The `incus` binary is stubbed via `dummy_commands/incus`, and the
host-level prep (`roles/_incus_host_setup`) is skipped.

`python3-yaml` + `python3-jsonschema` (ivm's host deps) are pre-seeded into the
sandbox baseline via `extra_packages_apt`, so the role's probe-gated install
becomes a no-op and the before/after diff only shows files the role wrote.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402

SANDBOX_DIR = Path(__file__).resolve().parents[1]
DUMMY_COMMANDS_DIR = SANDBOX_DIR / "dummy_commands"


CONFIG = SandboxConfig(
    name="incus_vm",
    description="ivm engine install (binary + schema + templates + dotfiles staging) + round-trip uninstall (incus binary stubbed; host-level daemon/group setup skipped).",
    playbook=Path("playbooks/incus_vm.yml"),
    dummy_commands=[
        DUMMY_COMMANDS_DIR / "incus",
    ],
    # ivm's host deps; pre-seeded so the role's probe-gated install is a no-op.
    extra_packages_apt=["python3-yaml", "python3-jsonschema"],
    # Skip the shared host-level prep done by `roles/_incus_host_setup`
    # (apt install + systemd incus.service + `incus admin init`), none of
    # which work inside a rootless podman container.
    extra_ansible_vars={"incus_vm_skip_host_setup": True},
    unapply_playbook=Path("playbooks/incus_vm_uninstall.yml"),
    unapply_ansible_vars={"incus_vm_skip_host_setup": True},
)
