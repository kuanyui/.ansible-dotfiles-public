"""Sandbox config for `playbooks/apparmor.yml`.

Verifies AppArmor profile deployment paths and runs `apparmor_parser
--skip-kernel-load` against every deployed profile to catch syntax errors
before they hit the real host.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Allow sibling import of config.py when discovered.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parents[3]
SANDBOX_DIR = Path(__file__).resolve().parents[1]
DUMMY_COMMANDS_DIR = SANDBOX_DIR / "dummy_commands"
DENY_PERSONAL_DIRS = PROJECT_DIR / "roles" / "apparmor" / "local_vars" / "deny_personal_dirs.aa"


def _pre_flight(project_dir: Path) -> None:
    if not DENY_PERSONAL_DIRS.exists():
        raise SystemExit(
            f"ERROR: {DENY_PERSONAL_DIRS} not found.\n"
            f"  Run: python3 scripts/gen_deny_personal_dirs.py <path> [<path> ...]"
        )


def _post_check_apparmor_syntax(project_dir: Path, container) -> int:
    """Run `apparmor_parser --skip-kernel-load` on every /etc/apparmor.d/local_*
    file the playbook deployed. Pure-userspace validation: catches syntax errors
    and missing `#include` targets without needing kernel AppArmor support.
    """
    script = r"""
        errors=0
        total=0
        while IFS= read -r profile; do
            total=$((total + 1))
            name=$(basename "$profile")
            if /usr/sbin/apparmor_parser --skip-kernel-load "$profile" >/tmp/aa_check.log 2>&1; then
                printf "  OK    %s\n" "$name"
            else
                printf "  FAIL  %s\n" "$name"
                sed "s/^/        /" /tmp/aa_check.log
                errors=$((errors + 1))
            fi
        done < <(find /etc/apparmor.d -maxdepth 1 -name "local_*" -type f 2>/dev/null | sort)
        printf "  %d/%d profiles passed.\n" "$((total - errors))" "$total"
        exit $errors
    """
    result = container.ssh("sudo", "bash", "-c", script, check=False)
    return result.returncode


CONFIG = SandboxConfig(
    name="apparmor",
    description="AppArmor profile deployment + apparmor_parser --skip-kernel-load syntax validation.",
    playbook=Path("playbooks/apparmor.yml"),
    snapshot_paths=[
        "/etc/apparmor.d",
        "/home/sandboxuser/.local",
        "/usr/local/share/applications",
    ],
    extra_packages_apt=["apparmor"],
    dummy_commands=[
        DUMMY_COMMANDS_DIR / cmd
        for cmd in ("apparmor_parser", "aa-enforce", "aa-status", "aa-disable", "aa-complain")
        # NOTE: not stubbing systemctl - the sandbox image runs real systemd as PID 1,
        # so `systemctl reload apparmor` etc. work for real (apparmor service may not
        # actually load profiles into kernel without LSM, but the systemd-side
        # bookkeeping completes normally).
    ],
    extra_files={
        # The Firefox profile-discovery task expects this. Skipped silently
        # by SandboxConfig if the host doesn't have Firefox installed.
        Path.home() / ".mozilla/firefox/profiles.ini":
            "/home/sandboxuser/.mozilla/firefox/profiles.ini",
    },
    extra_ansible_vars={"setup_apparmor": "true"},
    pre_flight=_pre_flight,
    post_check=_post_check_apparmor_syntax,
)
