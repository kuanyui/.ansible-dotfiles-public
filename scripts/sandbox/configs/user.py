"""Sandbox config for `playbooks/user.yml`.

Provisions current user with zsh + emacs + dotfiles. The `container_apps` and
`apparmor` roles are also in this playbook but gated off by default in
`group_vars/all.yml` (`setup_container_apps` / `setup_apparmor` both false) and
have dedicated sandbox configs of their own, so they are intentionally not
exercised here.

`user.yml` runs with `is_root: false`, which skips the install-* sub-tasks
in `zsh` / `emacs` (those only fire when `is_root: true`); only the config
deployment paths run. That means no apt packages are needed in the sandbox.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402


CONFIG = SandboxConfig(
    name="user",
    description="zsh + emacs + dotfiles deployment for the current user (is_root=false path).",
    playbook=Path("playbooks/user.yml"),
)
