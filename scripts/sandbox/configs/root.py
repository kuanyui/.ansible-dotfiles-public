"""Sandbox config for `playbooks/root.yml`.

Provisions root with packages + zsh + emacs + dotfiles. `is_root: true` so the
`zsh` / `emacs` roles run their install-* sub-tasks (apt-install + `user:`
shell change) in addition to config deployment.

`packages_install_sys_tools` / `packages_install_net_tools` are disabled in
the sandbox to keep runs fast - those install ~10 mostly-large packages
(nethogs, tcpdump, nvtop, sysstat, ...) that aren't useful for verifying YAML
correctness. `packages_install_basic_tools` stays on so the package-install
code path is still exercised against a small set (git/make/ripgrep/tmux/stow).

emacs picks `emacs-nox` automatically because `sandbox.py` injects
`has_gui_support=false` globally (sandbox is headless), saving the GTK deps.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402


CONFIG = SandboxConfig(
    name="root",
    description="packages + zsh + emacs + dotfiles for root (is_root=true path).",
    playbook=Path("playbooks/root.yml"),
    extra_ansible_vars={
        "packages_install_sys_tools": "false",
        "packages_install_net_tools": "false",
        "packages_install_wayland_tools": "false",
    },
)
