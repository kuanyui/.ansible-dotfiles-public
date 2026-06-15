"""Sandbox config for `playbooks/vm_podman.yml`.

Installs the `pvm` launcher + completions and co-produces the shared
provision-asset cache under `~/.local/share/ansible-managed/`. Pure file
deployment + JSON/dotfiles rendering - the role does NOT drive `podman` at
install time, so the sandbox needs no podman binary; `vm_podman_skip_host_setup`
skips the host podman package install.

Round-trip: deploy via vm_podman.yml, then uninstall via the dedicated uninstall
playbook. The harness diffs the post-uninstall filesystem against the pre-deploy
baseline; any leftover means a `state: absent` task (or the ref-counted shared
cache cleanup) was missed. In the sandbox neither `ivm` nor `qvm` is installed,
so the 3-way ref-count removes the shared cache on uninstall (back to baseline).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402


CONFIG = SandboxConfig(
    name="vm_podman",
    description="pvm launcher + completions + shared provision-asset cache deployment.",
    playbook=Path("playbooks/vm_podman.yml"),
    extra_ansible_vars={"vm_podman_skip_host_setup": True},
    unapply_playbook=Path("playbooks/vm_podman_uninstall.yml"),
    unapply_ansible_vars={"vm_podman_skip_host_setup": True},
)
