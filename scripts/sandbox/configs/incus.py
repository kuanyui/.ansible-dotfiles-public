"""Sandbox config for `playbooks/incus.yml`.

Verifies the role-level concerns of `roles/incus`: schema asserts pass,
`v-<agent>` launchers + completions get rendered to the right places, the
install manifest is well-formed, and the uninstall path cleans them back to
the pre-apply baseline.

What we deliberately DON'T test here: the launcher's actual VM lifecycle
(incus launch / virtio-fs share / curl-install agent inside VM). Doing that
inside the sandbox would need nested KVM through libkrun or crun, which is
brittle and orthogonal to what this sandbox is meant to catch. The `incus`
binary is stubbed via `dummy_commands/incus` just enough to satisfy the
role's pre-flight `incus --version` check.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402

SANDBOX_DIR = Path(__file__).resolve().parents[1]
DUMMY_COMMANDS_DIR = SANDBOX_DIR / "dummy_commands"


CONFIG = SandboxConfig(
    name="incus",
    description="v-<agent> Incus VM launcher install + manifest + round-trip uninstall (incus binary stubbed; host-level daemon/group setup skipped).",
    playbook=Path("playbooks/incus.yml"),
    dummy_commands=[
        DUMMY_COMMANDS_DIR / "incus",
    ],
    # Skip the host_setup.yml include - it needs real apt install + systemd
    # incus.service + `incus admin init` (KVM/network), none of which work
    # inside a rootless podman container. The launcher render half of the
    # role still runs and is what we're actually verifying.
    extra_ansible_vars={"incus_skip_host_setup": True},
    unapply_playbook=Path("playbooks/incus_uninstall.yml"),
    unapply_ansible_vars={"incus_skip_host_setup": True},
)
