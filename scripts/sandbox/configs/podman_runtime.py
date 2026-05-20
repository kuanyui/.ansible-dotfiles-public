"""Sandbox config for `playbooks/podman.yml`.

Verifies the file-level outcome of the podman OCI-runtime configuration:
deploy a managed `containers.conf` selecting libkrun as the default runtime,
then on idempotence re-run prove the file isn't rewritten. The role's
assertions about `crun` being built with `+LIBKRUN` and `podman info`
reporting `krun` as the effective runtime are kept on (sandbox can't actually
satisfy them on a rootless container with no libkrun); `crun` and `podman`
are stubbed in `dummy_commands/` to return canned values so the assertions
pass and the file-writing tasks downstream of them actually execute.

The role's openSUSE-only zypper install branch (`rpm -q libkrun1 ...`) is
skipped automatically by its own `when: ansible_facts['os_family'] == 'Suse'`
guard - sandbox image is Debian so those tasks short-circuit.

`podman_runtime: libkrun` + `podman_set_default_runtime: true` are forced via
extra_ansible_vars so we actually exercise the write path (defaults would
remove the file instead).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402

SANDBOX_DIR = Path(__file__).resolve().parents[1]
DUMMY_COMMANDS_DIR = SANDBOX_DIR / "dummy_commands"


CONFIG = SandboxConfig(
    name="podman_runtime",
    description="`containers.conf` write under user scope when libkrun is selected (assertions stubbed).",
    playbook=Path("playbooks/podman.yml"),
    dummy_commands=[
        DUMMY_COMMANDS_DIR / "crun",
        DUMMY_COMMANDS_DIR / "podman",
    ],
    extra_ansible_vars={
        "podman_runtime": "libkrun",
        "podman_set_default_runtime": "true",
        # `podman_runtime_scope: user` is the default and writes to
        # `~/.config/containers/containers.conf`, which the sandboxuser can
        # touch without needing sudo. `system` scope would need
        # `/etc/containers/containers.conf` (root-owned) and is left for a
        # separate sandbox config if desired.
    },
)
