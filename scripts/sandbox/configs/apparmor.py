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
PERSONAL_DIRS_YML = PROJECT_DIR / "roles" / "apparmor" / "local_vars" / "personal_dirs.yml"
DENY_PERSONAL_DIRS = PROJECT_DIR / "roles" / "apparmor" / "local_vars" / "deny_personal_dirs.aa"
CHECK_DENY_PERSONAL_DIRS = PROJECT_DIR / "scripts" / "check_deny_personal_dirs.py"


_SCAFFOLD_PERSONAL_DIRS_YML = PROJECT_DIR / "scripts" / "gen_personal_dirs_definitions_yaml.py"
_SCAFFOLD_DENY_PERSONAL_DIRS = PROJECT_DIR / "scripts" / "gen_deny_personal_dirs.py"


def _missing_input_file(missing: Path, scaffolder: Path, extra_note: str = "") -> "SystemExit":
    """Print a copy-pasteable error then defer to the scaffolder's own --help."""
    print(f"ERROR: {missing} not found.", file=sys.stderr)
    if extra_note:
        print(extra_note, file=sys.stderr)
    print("", file=sys.stderr)
    subprocess.run([sys.executable, str(scaffolder), "--help"])
    return SystemExit(1)


def _pre_flight(project_dir: Path) -> None:
    # Mirror Makefile `apply-apparmor`: existence check for the new YAML
    # pipeline, then the same existence + bare-x lint for the DEPRECATED `.aa`
    # (still required while `local_mixin_container_base` depends on the old
    # single-mixin abstraction).
    #
    # Schema validation of the YAML happens inside the playbook (gated by
    # `python3-jsonschema` install via `ansible.builtin.package`), not here -
    # this pre-flight only runs stdlib-safe checks.
    if not PERSONAL_DIRS_YML.exists():
        raise _missing_input_file(PERSONAL_DIRS_YML, _SCAFFOLD_PERSONAL_DIRS_YML)

    if not DENY_PERSONAL_DIRS.exists():
        raise _missing_input_file(
            DENY_PERSONAL_DIRS,
            _SCAFFOLD_DENY_PERSONAL_DIRS,
            extra_note="(still required while container_base mixin uses it - DEPRECATED).",
        )
    # `apparmor_parser` only catches invalid policy modes (e.g. `d` copied
    # from an audit-log mask) at kernel load time, which `--skip-kernel-load`
    # in the post-check skips - so this lint is the only place the bare-x
    # syntax issue can be caught inside the sandbox.
    result = subprocess.run(
        [sys.executable, str(CHECK_DENY_PERSONAL_DIRS)],
        cwd=str(project_dir),
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


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
    # `python3-jsonschema` is a hard runtime dep of the builder script
    # (gen_personal_dirs_aa_mixins.py) that the playbook invokes; without
    # it, the role's command task crashes with ModuleNotFoundError. The
    # Makefile's `_ensure-python3-jsonschema` covers the host (where the
    # pre_flight runs); this covers the sandbox image (where the playbook
    # runs).
    extra_packages_apt=["apparmor", "python3-jsonschema"],
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
