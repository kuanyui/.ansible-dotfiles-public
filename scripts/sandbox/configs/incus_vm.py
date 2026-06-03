"""Sandbox config for `playbooks/incus_vm.yml`.

Verifies the role-level concerns of `roles/incus_vm`: schema asserts
pass, `v-<workstation>` launchers + completions get rendered to the right
places, the install manifest is well-formed, and the uninstall path cleans
them back to the pre-apply baseline.

What we deliberately DON'T test here: the launcher's actual VM lifecycle
(incus launch / virtio-fs share / apt install / SPICE display). Doing that
inside the sandbox would need nested KVM and a host display server, which
is brittle and orthogonal to what this sandbox is meant to catch. The
`incus` binary is stubbed via `dummy_commands/incus`.

Note: with the default empty `incus_vm: []`, this sandbox renders
zero launchers - the apply still succeeds (no entries means nothing to
render) and the round-trip uninstall is also a clean no-op. To actually
exercise the launcher render in the sandbox, override
`-e incus_vm='[{...}]'` or uncomment examples in defaults.
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
    description="v-<workstation> Incus persistent VM launcher install + manifest + round-trip uninstall (incus binary stubbed; host-level daemon/group setup skipped).",
    playbook=Path("playbooks/incus_vm.yml"),
    dummy_commands=[
        DUMMY_COMMANDS_DIR / "incus",
    ],
    # Skip the shared host-level prep done by `roles/_incus_host_setup`
    # (apt install + systemd incus.service + `incus admin init`), none of
    # which work inside a rootless podman container.
    extra_ansible_vars={"incus_vm_skip_host_setup": True},
    unapply_playbook=Path("playbooks/incus_vm_uninstall.yml"),
    unapply_ansible_vars={"incus_vm_skip_host_setup": True},
)
