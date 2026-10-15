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

SANDBOX_DIR = Path(__file__).resolve().parents[1]
DUMMY_COMMANDS_DIR = SANDBOX_DIR / "dummy_commands"


def _pre_flight(project_dir: Path) -> None:
    """Preview `customized_extra_dirs.yml` + schema-validate it BEFORE any container
    work (image build, apt install, project copy - the ~1-2 min preamble).
    Lets the user `Ctrl+C` immediately if the YAML looks wrong, instead of
    paying the container-setup cost only to see the preview from inside the
    playbook later.

    The validator script self-bootstraps `python3-jsonschema` via sudo when
    missing (see `_ensure_jsonschema()` inside it), so sandbox does not
    duplicate that logic."""
    validator = project_dir / "roles" / "apparmor" / "scripts" / "gen_customized_extra_dirs_aa_mixins.py"
    subprocess.run([sys.executable, str(validator), "--validate-only"], check=True)


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


def _post_check_seccomp_derive(project_dir: Path, container) -> int:
    """Verify tasks/seccomp.yml derived a correct hardened .desktop from the stub
    source planted in post_setup_commands. Exercises the riskiest logic - the
    Exec/Name/DBusActivatable rewrite + the
    THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY token - which the
    apparmor_parser syntax check never touches.
    """
    derived = "/home/sandboxuser/.local/share/applications/org.telegram.desktop.desktop"
    script = f"""
        f="{derived}"
        fail=0
        if [ ! -f "$f" ]; then echo "  FAIL  seccomp derive: $f missing (derive skipped?)"; exit 1; fi
        head -1 "$f" | grep -q 'THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY' || {{ echo "  FAIL  no token on line 1"; fail=1; }}
        grep -Eq '^Exec=.*/seccomp-launch +LIBGL_ALWAYS_SOFTWARE=1 ' "$f" || {{ echo "  FAIL  Exec not routed through seccomp-launch + extra_env"; fail=1; }}
        grep -q '^DBusActivatable=false' "$f" || {{ echo "  FAIL  DBusActivatable not forced false"; fail=1; }}
        grep -q ' (hardened)' "$f" || {{ echo "  FAIL  Name not suffixed (hardened)"; fail=1; }}
        if [ "$fail" -eq 0 ]; then echo "  OK    seccomp derive: token + seccomp-launch Exec + DBusActivatable=false + (hardened)"; fi
        exit $fail
    """
    return container.exec("bash", "-c", script, user="root", check=False).returncode


def _post_check_aaa_rpmnew(project_dir: Path, container) -> int:
    """Verify the aaa-rpmnew helper deployed and classifies + acts correctly.

    Plants a normal distro update (`faketool.rpmnew`) and a resurrected shadowed profile
    (`chromium`, in apparmor_shadowed_system_profiles) into /etc/apparmor.d/, runs
    `aaa-rpmnew --yes`, then asserts: faketool was ADOPTED (.rpmnew -> bare) and chromium was
    NEUTRALIZED (removed from /etc/apparmor.d/ + backed up). Exercises the real
    mv / cp / rm / apparmor_parser --remove / systemctl reload path, not just --dry-run.
    Fixtures are cleaned up after. Without this the riskiest logic (ADOPT-vs-NEUTRALIZE
    classification from the baked-in shadow list) would ship untested.
    """
    tool = "/usr/local/sbin/aaa-rpmnew"
    backup = "/etc/apparmor.d/_backup_of_default_profiles_from_package_manager"
    script = f"""
        set -u
        fail=0
        if [ ! -x "{tool}" ]; then echo "  FAIL  {tool} missing or not executable"; exit 1; fi
        sed -n '2p' "{tool}" | grep -q 'THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY' \
            || {{ echo "  FAIL  managed marker not on line 2"; fail=1; }}
        # Simulate post-update state: a normal distro update + a resurrected shadowed profile.
        printf 'profile faketool /usr/bin/faketool {{\\n}}\\n' > /etc/apparmor.d/faketool.rpmnew
        printf 'profile chromium /usr/bin/chromium {{\\n}}\\n' > /etc/apparmor.d/chromium
        if ! "{tool}" --yes >/tmp/aaa_rpmnew.log 2>&1; then
            echo "  FAIL  aaa-rpmnew --yes exited non-zero"; sed 's/^/        /' /tmp/aaa_rpmnew.log; fail=1
        fi
        [ -f /etc/apparmor.d/faketool ]          || {{ echo "  FAIL  faketool not adopted"; fail=1; }}
        [ ! -e /etc/apparmor.d/faketool.rpmnew ] || {{ echo "  FAIL  faketool.rpmnew not consumed"; fail=1; }}
        [ ! -e /etc/apparmor.d/chromium ]        || {{ echo "  FAIL  shadowed chromium not removed"; fail=1; }}
        [ -f {backup}/chromium ]                 || {{ echo "  FAIL  chromium not backed up"; fail=1; }}
        rm -f /etc/apparmor.d/faketool "{backup}/chromium"
        if [ "$fail" -eq 0 ]; then echo "  OK    aaa-rpmnew: deploy + marker + ADOPT(faketool) + NEUTRALIZE(chromium)"; fi
        exit $fail
    """
    return container.exec("bash", "-c", script, user="root", check=False).returncode


def _post_check_orphan_cleanup(project_dir: Path, container) -> int:
    """Verify _install.yml's idempotent cleanup removed the orphaned local_* profile planted
    in post_setup_commands (`local_orphan_probe_delete_me` - not in any managed list).

    Asserts the file is gone from /etc/apparmor.d/. This guards the cleanup's allowlist logic
    (the set_fact basename allowlist + the `not in` conditions): a bug there either fails to
    delete the orphan or, worse, deletes a managed profile. The companion `--remove` unload step
    that now runs first cannot be asserted here - this container has no kernel AppArmor - so this
    check covers only the disk-level outcome. A second assertion confirms a MANAGED profile
    (`local_pathbased_chromium`, deployed by the same run) still exists, proving the allowlist
    did not over-delete.
    """
    orphan = "/etc/apparmor.d/local_orphan_probe_delete_me"
    managed = "/etc/apparmor.d/local_pathbased_chromium"
    script = f"""
        fail=0
        [ ! -e "{orphan}" ] || {{ echo "  FAIL  orphan {orphan} not deleted by cleanup"; fail=1; }}
        [ -f "{managed}" ]  || {{ echo "  FAIL  managed {managed} missing (allowlist over-deleted?)"; fail=1; }}
        if [ "$fail" -eq 0 ]; then echo "  OK    orphan cleanup: local_orphan_probe_delete_me removed, local_pathbased_chromium kept"; fi
        exit $fail
    """
    return container.exec("bash", "-c", script, user="root", check=False).returncode


def _post_check_qtwebengine(project_dir: Path, container) -> int:
    """Verify the QtWebEngineProcess hardening deployed correctly.

    Three things the task must get right:
    1. The distro `QtWebEngineProcess` (planted flags=(unconfined) in post_setup_commands) is
       neutralized: removed from /etc/apparmor.d/ and backed up (it would otherwise collide with
       our glob-attached profile on the same renderer binary).
    2. Our `local_pathbased_qtwebengineprocess` deployed AND still carries `flags=(complain)`.
       This is the load-bearing assertion: it ships as a default-deny (enforce) DRAFT in complain
       mode so it can be tuned on a real machine without breaking apps. The mode step in
       _install.yml runs aa-enforce over the managed profile list; if this profile were (wrongly)
       included there, aa-enforce would rewrite its header and strip `flags=(complain)`, silently
       promoting an untuned profile to enforce and breaking every Qt webview. It is registered in
       apparmor_template_profile_names_own_flags_mode precisely to be EXCLUDED from that step; this
       check fails loudly if that exclusion regresses.
    3. It includes local_mixin_kernel_surface_browser (chromium's `userns create,` + sandbox
       capabilities live there - without it the renderer's content-process sandbox cannot start).
    """
    ours = "/etc/apparmor.d/local_pathbased_qtwebengineprocess"
    vendor = "/etc/apparmor.d/QtWebEngineProcess"
    backup = "/etc/apparmor.d/_backup_of_default_profiles_from_package_manager/QtWebEngineProcess"
    script = f"""
        fail=0
        [ ! -e "{vendor}" ] || {{ echo "  FAIL  distro {vendor} not neutralized (still present)"; fail=1; }}
        [ -f "{backup}" ]   || {{ echo "  FAIL  distro QtWebEngineProcess not backed up"; fail=1; }}
        [ -f "{ours}" ]     || {{ echo "  FAIL  {ours} not deployed"; exit 1; }}
        head -4 "{ours}" | grep -q 'THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY' \
            || {{ echo "  FAIL  managed marker missing"; fail=1; }}
        grep -q 'flags=(complain)' "{ours}" \
            || {{ echo "  FAIL  flags=(complain) missing - mode step promoted the draft to enforce?"; fail=1; }}
        grep -q 'local_mixin_kernel_surface_browser' "{ours}" \
            || {{ echo "  FAIL  kernel_surface_browser include missing - userns/sandbox would break"; fail=1; }}
        if [ "$fail" -eq 0 ]; then echo "  OK    qtwebengine: distro neutralized + local_ deployed in complain draft + sandbox include intact"; fi
        exit $fail
    """
    return container.exec("bash", "-c", script, user="root", check=False).returncode


def _post_check_aaa_logs(project_dir: Path, container) -> int:
    """Verify the aaa-logs helper deployed and runs. Smoke test: executable, carries the
    managed marker, `aaa-logs 5` exits 0 (no denials in a fresh sandbox is fine - the read
    pipe ends in `|| true`), and a non-numeric argument is rejected with usage (exit 2)."""
    tool = "/usr/local/bin/aaa-logs"
    script = f"""
        set -u
        fail=0
        if [ ! -x "{tool}" ]; then echo "  FAIL  {tool} missing or not executable"; exit 1; fi
        sed -n '2p' "{tool}" | grep -q 'THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY' \
            || {{ echo "  FAIL  managed marker not on line 2"; fail=1; }}
        if ! "{tool}" 5 >/tmp/aaa_logs.log 2>&1; then
            echo "  FAIL  aaa-logs 5 exited non-zero"; sed 's/^/        /' /tmp/aaa_logs.log; fail=1
        fi
        if "{tool}" notanumber >/dev/null 2>&1; then echo "  FAIL  non-numeric arg not rejected"; fail=1; fi
        if [ "$fail" -eq 0 ]; then echo "  OK    aaa-logs: deploy + marker + runs + rejects bad arg"; fi
        exit $fail
    """
    return container.exec("bash", "-c", script, user="root", check=False).returncode


def _post_check_handy_complain_draft(project_dir: Path, container) -> int:
    """Verify local_pathbased_handy deployed as the COMPLAIN draft it is meant to be.

    `flags=(complain)` is load-bearing: the profile was authored from source, never audited, so
    it must log (not block) until tuned. It is registered in
    apparmor_template_profile_names_own_flags_mode precisely to be EXCLUDED from the aa-enforce
    step in _install.yml; this check fails loudly if that exclusion regresses (aa-enforce would
    rewrite the header and strip the flag, silently promoting an untuned profile). The second
    assertion covers the one rule that must bite even in complain mode: the audit deny on
    pkexec, the in-app updater's escalation path.
    """
    ours = "/etc/apparmor.d/local_pathbased_handy"
    script = f"""
        fail=0
        [ -f "{ours}" ] || {{ echo "  FAIL  {ours} not deployed"; exit 1; }}
        head -4 "{ours}" | grep -q 'THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY' \
            || {{ echo "  FAIL  managed marker missing"; fail=1; }}
        grep -q '^profile local_pathbased_handy /usr/bin/handy flags=(complain) {{' "{ours}" \
            || {{ echo "  FAIL  flags=(complain) header missing - mode step promoted the draft to enforce?"; fail=1; }}
        grep -q '^ *audit deny /usr/bin/pkexec x,' "{ours}" \
            || {{ echo "  FAIL  audit deny on pkexec missing - the in-app updater could escalate"; fail=1; }}
        if [ "$fail" -eq 0 ]; then echo "  OK    handy: complain draft intact (marker + flags=(complain) + pkexec audit deny)"; fi
        exit $fail
    """
    return container.exec("bash", "-c", script, user="root", check=False).returncode


def _post_check_all(project_dir: Path, container) -> int:
    """AppArmor profile syntax validation + seccomp-derive + aaa-rpmnew + aaa-logs + orphan
    cleanup + qtwebengine hardening + the handy complain draft, combined so a single post_check
    covers all. Returns the sum of return codes (non-zero fails)."""
    return (
        _post_check_apparmor_syntax(project_dir, container)
        + _post_check_seccomp_derive(project_dir, container)
        + _post_check_aaa_rpmnew(project_dir, container)
        + _post_check_aaa_logs(project_dir, container)
        + _post_check_orphan_cleanup(project_dir, container)
        + _post_check_qtwebengine(project_dir, container)
        + _post_check_handy_complain_draft(project_dir, container)
    )


CONFIG = SandboxConfig(
    name="apparmor",
    description="AppArmor profile deployment + apparmor_parser --skip-kernel-load syntax validation.",
    playbook=Path("playbooks/apparmor.yml"),
    # `python3-jsonschema` is a hard runtime dep of the builder script
    # (gen_customized_extra_dirs_aa_mixins.py) that the playbook invokes; without
    # it, the role's command task crashes with ModuleNotFoundError. The
    # script's own `_ensure_jsonschema()` handles the host side (triggered
    # during _pre_flight's --validate-only call); this covers the sandbox
    # image (where the playbook runs inside the container).
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
    extra_ansible_vars={
        "setup_apparmor": True,
        # Skip the role's preview+confirm pause - sandbox does the same
        # preview in `_pre_flight` above, BEFORE any container work happens.
        "apparmor_non_interactive": True,
    },
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
        # Plant a stub distro Telegram .desktop so tasks/seccomp.yml's derive ALWAYS
        # runs in the sandbox - the real app is never installed here, and without a
        # source the derive (the riskiest logic: Exec/Name/DBusActivatable rewrite)
        # would silently skip and never be tested. DBusActivatable=true + a
        # [Desktop Action] are included on purpose so neutralization + per-action
        # Exec rewrite are covered. Asserted by _post_check_seccomp_derive below.
        ["bash", "-c",
         "mkdir -p /usr/share/applications && cat > /usr/share/applications/org.telegram.desktop.desktop <<'EOF'\n"
         "[Desktop Entry]\n"
         "Version=1.0\n"
         "Type=Application\n"
         "Name=Telegram Desktop\n"
         "GenericName=Messaging\n"
         "TryExec=Telegram\n"
         "Exec=Telegram -- %u\n"
         "Icon=org.telegram.desktop\n"
         "Terminal=false\n"
         "Categories=Network;InstantMessaging;Qt;\n"
         "MimeType=x-scheme-handler/tg;\n"
         "DBusActivatable=true\n"
         "Actions=quit;\n"
         "StartupWMClass=TelegramDesktop\n"
         "\n"
         "[Desktop Action quit]\n"
         "Name=Quit Telegram\n"
         "Exec=Telegram -quit\n"
         "EOF"],
        # Plant an ORPHANED role profile: a syntactically valid local_* file that is NOT in any
        # of the role's managed lists (defaults/main.yml). It stands in for a profile the role
        # deployed under a name it later dropped/renamed. The _install.yml cleanup must unload it
        # from the kernel AND delete the file; _post_check_orphan_cleanup asserts the deletion.
        # (The kernel unload itself is not observable here - this container has no kernel AppArmor,
        # which is why the syntax check uses --skip-kernel-load and apparmor.service is a stub.)
        ["bash", "-c",
         "cat > /etc/apparmor.d/local_orphan_probe_delete_me <<'EOF'\n"
         "# THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY (sandbox orphan-cleanup fixture)\n"
         "abi <abi/3.0>,\n"
         "#include <tunables/global>\n"
         "profile local_orphan_probe_delete_me {\n"
         "}\n"
         "EOF"],
        # Plant the distro `QtWebEngineProcess` profile (flags=(unconfined), the real vendor
        # shape) so tasks/qtwebengineprocess.yml's neutralize step has something to back up +
        # remove. _post_check_qtwebengine asserts it was neutralized and that our replacement
        # deployed with flags=(default_allow) intact (not clobbered to enforce by the mode step).
        ["bash", "-c",
         "cat > /etc/apparmor.d/QtWebEngineProcess <<'EOF'\n"
         "abi <abi/3.0>,\n"
         "#include <tunables/global>\n"
         "profile QtWebEngineProcess /usr/lib/qt6/libexec/QtWebEngineProcess flags=(unconfined) {\n"
         "  userns,\n"
         "}\n"
         "EOF"],
    ],
    pre_flight=_pre_flight,
    post_check=_post_check_all,
)
