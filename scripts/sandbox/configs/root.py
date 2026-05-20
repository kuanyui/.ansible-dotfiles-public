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

Every package the playbook itself would install is mirrored in
`extra_packages_apt` below, so the sandbox baseline already contains all the
`/usr/*` files from those packages. After that, the playbook's apt tasks
become no-ops and the before/after diff is clean: only deploy-task writes to
`/root/`, `/etc/passwd`, `/etc/zsh/`, etc. appear - no apt noise. The full
`/usr/` tree is in the snapshot scope, so a `dest:` typo writing to
`/usr/bin/<x>` or `/usr/share/<x>` would also show up immediately.
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
    # Mirror every apt package the playbook itself would install, so they're
    # in the sandbox baseline BEFORE the before-snapshot. With this, the
    # playbook's apt tasks become no-ops (`already installed`) and the diff
    # contains only files the role's deploy tasks actually wrote - no /usr/bin
    # or /usr/share noise. Drift is self-flagging: if a package is added to
    # role defaults but not here, the playbook will install it at runtime and
    # the new /usr/* files will appear in the diff, telling you to sync this
    # list.
    extra_packages_apt=[
        # `packages_basic_tools.common` (roles/packages/defaults/main.yml).
        # sys/net/wayland are gated off in extra_ansible_vars below, so their
        # package lists aren't needed here.
        "git", "make", "ripgrep", "tmux", "stow",
        # zsh install + plugins (roles/zsh/tasks/install-zsh-from-distro-repo.yml).
        "zsh", "zsh-syntax-highlighting", "zsh-autosuggestions",
        # emacs install (roles/emacs/tasks/install-emacs-from-distro-repo.yml).
        # has_gui_support=false (injected by sandbox.py) picks `emacs-nox`
        # via the ternary in roles/emacs/defaults/main.yml.
        "emacs-nox",
        # `emacs_packages_debian` (roles/emacs/defaults/main.yml).
        "elpa-helm-core", "elpa-vertico", "elpa-marginalia", "elpa-orderless",
        "elpa-magit", "elpa-diff-hl", "elpa-rainbow-delimiters",
        "elpa-markdown-mode", "elpa-systemd", "elpa-company",
        "elpa-flycheck", "elpa-dockerfile-mode", "elpa-git-commit",
        "elpa-jinja2-mode", "elpa-projectile",
    ],
    extra_ansible_vars={
        "packages_install_sys_tools": "false",
        "packages_install_net_tools": "false",
        "packages_install_wayland_tools": "false",
    },
)
