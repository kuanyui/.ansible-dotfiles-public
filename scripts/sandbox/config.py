"""Sandbox configuration dataclass.

Each playbook that should be sandbox-runnable defines a `CONFIG = SandboxConfig(...)`
in its own file under `scripts/sandbox/configs/<name>.py`. The harness
(`scripts/sandbox/sandbox.py`) auto-discovers all such files at startup.

Private dotfiles repos can drop additional `<name>.py` configs into their own
`scripts/sandbox/configs/` and point the harness at them via
`SANDBOX_CONFIGS_EXTRA_DIR=/path/to/private/scripts/sandbox/configs`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from sandbox import Container


@dataclass
class SandboxConfig:
    # CLI selector: `python3 sandbox.py <name>`. Must be unique.
    name: str

    # One-line description for `--help`.
    description: str

    # Playbook to run, relative to project root.
    playbook: Path

    # Extra apt packages installed on top of the base sandbox image. Image
    # already has python3 + ansible-core + sudo + openssh-server + systemd.
    extra_packages_apt: list[str] = field(default_factory=list)

    # Host paths to executables that get copied into the container's
    # /usr/local/bin/. Use this to stub kernel-side ops (apparmor_parser etc.)
    # that have no equivalent inside a microVM sandbox.
    dummy_commands: list[Path] = field(default_factory=list)

    # Host file -> container path. Files that the playbook expects to find
    # but aren't part of the project tree (e.g. ~/.mozilla/firefox/profiles.ini).
    extra_files: dict[Path, str] = field(default_factory=dict)

    # Extra `-e VAR=VAL` passed to ansible-playbook. Useful to flip gates
    # (`setup_apparmor=true`, `setup_container_apps=true` etc.) for the dry-run.
    extra_ansible_vars: dict[str, Any] = field(default_factory=dict)

    # Commands run as `root` inside the container AFTER apt installs +
    # dummy_commands + extra_files copy, BUT BEFORE the project tree is copied
    # in. Used to patch up service files etc. that need to be overridden after
    # the packages installed by `extra_packages_apt` write them. Each entry is
    # an argv list (no shell). For shell features use `["bash", "-c", "..."]`.
    post_setup_commands: list[list[str]] = field(default_factory=list)

    # Called with project_dir on the host before any container action. Should
    # raise SystemExit (or any exception) to abort. Default: no-op.
    pre_flight: Callable[[Path], None] = field(default=lambda _: None)

    # Called with project_dir + Container handle after the playbook ran.
    # Return number of errors found. Default: no checks performed.
    post_check: Callable[[Path, "Container"], int] = field(default=lambda _, __: 0)
