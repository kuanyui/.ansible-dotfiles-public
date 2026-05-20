"""Sandbox config for `playbooks/apparmor.yml`.

Verifies AppArmor profile deployment paths and runs `apparmor_parser
--skip-kernel-load` against every deployed profile to catch syntax errors
before they hit the real host.
"""

from __future__ import annotations

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
    result = container.exec("bash", "-c", script, user="root", check=False)
    return result.returncode


CONFIG = SandboxConfig(
    name="apparmor",
    description="AppArmor profile deployment + apparmor_parser --skip-kernel-load syntax validation.",
    playbook=Path("playbooks/apparmor.yml"),
    extra_packages_apt=["apparmor"],
    dummy_commands=[
        DUMMY_COMMANDS_DIR / cmd
        for cmd in (
            # `systemctl` is NOT stubbed - real systemd runs as PID 1 in the
            # sandbox image (--runtime crun, not libkrun), so the role's
            # `notify: Reload apparmor` handler exercises real systemd plumbing.
            #
            # apparmor_parser / aa-* still ARE stubbed for two reasons that
            # both stand even with real systemd:
            #   1. They modify host kernel AppArmor LSM state, which requires
            #      `CAP_MAC_ADMIN` - rootless podman doesn't have this, so
            #      every real `aa-enforce` invocation would just error.
            #   2. The sandbox shares the host kernel (crun, not microVM), so
            #      even if it had the cap, real profile loads would clobber
            #      whatever profiles the host already has loaded.
            # The apparmor_parser stub passes USERSPACE flags (--parse, -p, -Q,
            # --preprocess) through to /usr/sbin/apparmor_parser so syntax
            # validation still happens for real; only kernel-load modes are
            # short-circuited. The post_check below also bypasses the stub via
            # absolute path to run --skip-kernel-load against every deployed
            # profile.
            "apparmor_parser",
            "aa-enforce", "aa-status", "aa-disable", "aa-complain",
        )
    ],
    extra_files={
        # The Firefox profile-discovery task expects this. Skipped silently
        # by SandboxConfig if the host doesn't have Firefox installed.
        Path.home() / ".mozilla/firefox/profiles.ini":
            "/home/sandboxuser/.mozilla/firefox/profiles.ini",
    },
    extra_ansible_vars={"setup_apparmor": True},
    # Full unit override for `apparmor.service` inside the sandbox. Reason: the
    # stock Debian unit has `AssertSecurity=apparmor` (and/or `ConditionSecurity=`),
    # which checks the kernel-level LSM state. In a rootless container
    # `/sys/kernel/security/` is masked, the assert fails, the service can't be
    # started, and the role's `notify: Reload apparmor` handler (`state:
    # reloaded`) fails with `Assertion failed on job for apparmor.service`.
    #
    # We write a complete replacement to `/etc/systemd/system/apparmor.service`,
    # which systemd loads in preference to `/lib/systemd/system/apparmor.service`
    # (the apt-installed file). No conditions, no asserts, ExecStart/Reload/Stop
    # are `/bin/true` - real profile loading is intentionally stubbed at the
    # binary level (see `dummy_commands` above), so the service-level operations
    # should be no-ops in the sandbox too. The smoke test (`systemctl start`)
    # at the end verifies the override is good before we hand off to the
    # playbook, so we fail fast here instead of inside the idempotence check.
    post_setup_commands=[
        ["bash", "-c",
         "cat > /etc/systemd/system/apparmor.service <<'EOF'\n"
         "[Unit]\n"
         "Description=Sandbox no-op stub for AppArmor service\n"
         "\n"
         "[Service]\n"
         "Type=oneshot\n"
         "RemainAfterExit=yes\n"
         "ExecStart=/bin/true\n"
         "ExecReload=/bin/true\n"
         "ExecStop=/bin/true\n"
         "\n"
         "[Install]\n"
         "WantedBy=multi-user.target\n"
         "EOF"],
        ["systemctl", "daemon-reload"],
        # Smoke test: prove the override works before the playbook runs. If
        # this fails, the sandbox aborts here (clearer than a vague handler
        # failure mid-playbook).
        ["systemctl", "start", "apparmor.service"],
        ["systemctl", "reload", "apparmor.service"],
    ],
    pre_flight=_pre_flight,
    post_check=_post_check_apparmor_syntax,
)
