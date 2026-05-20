#!/usr/bin/env python3
"""Dry-run any project playbook in a throwaway podman + systemd sandbox.

Runs the playbook against an isolated Debian container (default --runtime crun,
which gives real systemd as PID 1), captures a before/after file-tree diff of
paths the playbook touches, runs the playbook again to check idempotence, and
invokes any config-specific post-check (e.g. apparmor_parser --skip-kernel-load
for apparmor profile syntax).

Layer 2 hardening (host kernel attack-surface reduction - crun shares the host
kernel; microVM isolation would require Kata Containers, since libkrun is
incompatible with systemd-as-PID-1):
    user namespace                    rootless podman default (container's UID 0
                                      maps to host's unprivileged UID)
    default seccomp profile           rootless podman default (~50 dangerous
                                      syscalls blocked: kexec_load, create_module,
                                      ptrace into other namespaces, etc.)
    --cap-drop=NET_RAW                no raw-socket capability

These three are unconditional. We do NOT use `--security-opt apparmor=<X>` or
SELinux labels because the kernel LSM hooks require CAP_MAC_ADMIN, which
rootless podman doesn't have. For stronger isolation, switch the runtime to
Kata Containers (real microVM with its own kernel).

Usage:
    python3 scripts/sandbox/sandbox.py --help
    python3 scripts/sandbox/sandbox.py <config>
    python3 scripts/sandbox/sandbox.py apparmor
    python3 scripts/sandbox/sandbox.py user --runtime runc

Configs live in scripts/sandbox/configs/<name>.py with a module-level
`CONFIG = SandboxConfig(...)`. Private overlays can add configs via the
`SANDBOX_CONFIGS_EXTRA_DIR` env var.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

# Allow `from config import SandboxConfig` when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SandboxConfig  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parents[2]
SANDBOX_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE = "debian:trixie"
SANDBOX_USER = "sandboxuser"
IMAGE_TAG = "localhost/ansible-dotfiles-sandbox:latest"


# =============================================================================
# Container handle
# =============================================================================

class Container:
    """RAII wrapper for the podman lifecycle: build image, run, exec, cleanup."""

    def __init__(
        self,
        runtime: str | None,
        startup_timeout: int = 90,
        keep_container_on_exit: bool = False,
    ) -> None:
        # runtime: "crun" | "runc" | None (None = don't pass --runtime)
        # (krun is unsupported here: see Dockerfile rationale.)
        self.runtime = runtime
        self.name = f"ansible-sandbox-{os.getpid()}"
        self._startup_timeout = startup_timeout
        self._leave_running = keep_container_on_exit

    # ---------- lifecycle ----------

    def __enter__(self) -> "Container":
        self._build_image()
        self._run()
        self._wait_systemd_ready(timeout=self._startup_timeout)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._leave_running:
            return
        self._remove()

    def _build_image(self) -> None:
        print(f"==> Building sandbox image `{IMAGE_TAG}`...")
        subprocess.run(
            ["podman", "build", "--tag", IMAGE_TAG, str(SANDBOX_DIR)],
            check=True,
        )

    def _run(self) -> None:
        print(
            f"==> Starting container `{self.name}` "
            f"(runtime={self.runtime or 'system-default'})..."
        )
        cmd = [
            "podman", "run",
            "--name", self.name,
            "--detach",
            # Required for systemd-as-PID-1 to find /sys/fs/cgroup wired up.
            "--systemd=always",
            # Layer 2 hardening - drop NET_RAW (no raw sockets needed inside
            # sandbox). Rootless podman default still includes NET_RAW; this
            # removes it. AppArmor/SELinux profile switching is intentionally
            # NOT used: rootless podman can't (CAP_MAC_ADMIN required). The
            # remaining defenses - user namespace + default seccomp - are on
            # by podman default and we don't disable them.
            "--cap-drop", "NET_RAW",
        ]
        if self.runtime:
            cmd += ["--runtime", self.runtime]
        cmd.append(IMAGE_TAG)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    def _wait_systemd_ready(self, timeout: int) -> None:
        """Block until systemd inside container reaches 'running' or 'degraded'.

        Polls `systemctl is-system-running` over `podman exec`. Returns silently
        on success; dumps diagnostics + leaves container running on timeout.
        """
        deadline = time.monotonic() + timeout
        last_state = ""
        while time.monotonic() < deadline:
            try:
                r = self.exec(
                    "systemctl", "is-system-running",
                    user="root", check=False, capture_output=True,
                )
                last_state = (r.stdout or "").strip()
                # `running` = ideal; `degraded` = boot done but some units failed
                # (acceptable for sandbox - we'll still get realistic diff).
                if last_state in ("running", "degraded"):
                    print(f"==> systemd ready (state: {last_state}).")
                    return
            except subprocess.CalledProcessError:
                pass
            time.sleep(1)
        # Timeout - diagnose + leave container alive for inspection.
        print(
            f"\n!!! systemd inside `{self.name}` not ready within {timeout}s "
            f"(last state: {last_state or 'unknown'}).",
            file=sys.stderr,
        )
        print("\n--- `podman logs --tail 100 <name>` ---", file=sys.stderr)
        subprocess.run(["podman", "logs", "--tail", "100", self.name], check=False)
        print(
            f"\nContainer left running for inspection. To clean up:\n"
            f"  podman rm -f {self.name}\n",
            file=sys.stderr,
        )
        self._leave_running = True
        raise SystemExit(1)

    def _remove(self) -> None:
        subprocess.run(
            ["podman", "rm", "-f", self.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )

    # ---------- exec / cp ----------

    def exec(
        self,
        *cmd: str,
        user: str = SANDBOX_USER,
        check: bool = True,
        capture_output: bool = False,
        workdir: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a remote command via `podman exec`. Args are passed directly to
        execvp inside the container - no shell, no injection risk."""
        podman_cmd = ["podman", "exec", "--user", user]
        if workdir:
            podman_cmd += ["--workdir", workdir]
        podman_cmd.append(self.name)
        podman_cmd.extend(cmd)
        return subprocess.run(
            podman_cmd, check=check, capture_output=capture_output, text=True,
        )

    def cp_to(self, src: Path, container_dst: str) -> None:
        subprocess.run(
            ["podman", "cp", str(src), f"{self.name}:{container_dst}"],
            check=True,
        )

    def cp_from(self, container_src: str, dst: Path) -> None:
        subprocess.run(
            ["podman", "cp", f"{self.name}:{container_src}", str(dst)],
            check=True,
        )


# =============================================================================
# Helpers
# =============================================================================

def _snapshot(c: Container, paths: list[str], dst_host_file: Path) -> None:
    """Tar listed container paths into a file on the host."""
    if not paths:
        dst_host_file.write_bytes(b"")
        return
    remote_tar = f"/tmp/snap-{os.getpid()}.tgz"
    # `--ignore-failed-read` lets tar warn-then-continue on paths that don't
    # exist yet (typical for "before" snapshot of dirs the playbook will create)
    # and still exit 0. No shell needed; safe regardless of what `paths` contains.
    c.exec(
        "tar", "--ignore-failed-read", "-czf", remote_tar, *paths,
        user="root",
    )
    c.cp_from(remote_tar, dst_host_file)
    c.exec("rm", "-f", remote_tar, user="root")


def _extract(tar_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if tar_path.stat().st_size == 0:
        return
    with tarfile.open(tar_path, "r:gz") as t:
        t.extractall(out_dir)


def _print_diff(before: Path, after: Path) -> None:
    print()
    print("=" * 60)
    print(" SANDBOX DIFF  (before -> after)")
    print("=" * 60)
    diff_out = subprocess.run(
        ["diff", "-ruN", str(before), str(after)],
        capture_output=True, text=True,
    ).stdout
    # Strip the temp-dir prefixes so paths read as a/etc/... b/etc/...
    diff_out = (
        diff_out
        .replace(f"--- {before}/", "--- a/")
        .replace(f"+++ {after}/", "+++ b/")
        .replace(f"--- {before}", "--- a/")
        .replace(f"+++ {after}", "+++ b/")
    )
    if shutil.which("delta"):
        subprocess.run(["delta", "--paging=never"], input=diff_out, text=True)
    else:
        # color +/- lines via grep
        subprocess.run(
            ["grep", "--color=always", "-E", r"^(\+.*|-.*|@@.*)$|$"],
            input=diff_out, text=True,
        )
    # Summary of changed files. Classify each path as added (+, green),
    # removed (-, red), or modified (=, yellow) based on whether the file is
    # present in the before/after snapshot dirs. Container-absolute paths
    # restored with leading `/` (the tar extract strips it).
    print()
    print("-" * 60)
    print(" CHANGED FILES")
    print("-" * 60)
    GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
    classified: dict[str, str] = {}  # rel path -> "+" / "-" / "="
    lines = diff_out.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            old_tok = line.split("\t", 1)[0].split(" ", 1)[1]
            new_tok = lines[i + 1].split("\t", 1)[0].split(" ", 1)[1]
            old_rel = old_tok[2:] if old_tok.startswith(("a/", "b/")) else old_tok
            new_rel = new_tok[2:] if new_tok.startswith(("a/", "b/")) else new_tok
            in_before = old_tok != "/dev/null" and old_rel and (before / old_rel).exists()
            in_after = new_tok != "/dev/null" and new_rel and (after / new_rel).exists()
            if not in_before and in_after:
                classified[new_rel] = "+"
            elif in_before and not in_after:
                classified[old_rel] = "-"
            elif in_before and in_after:
                classified[new_rel] = "="
            i += 2
        else:
            i += 1
    color_map = {"+": GREEN, "-": RED, "=": YELLOW}
    for rel in sorted(classified):
        sym = classified[rel]
        print(f"  {color_map[sym]}{sym} /{rel}{RESET}")


def _ansible_playbook_argv(cfg: SandboxConfig) -> list[str]:
    extra_var_args: list[str] = []
    for k, v in cfg.extra_ansible_vars.items():
        extra_var_args += ["-e", f"{k}={v}"]
    return [
        "ansible-playbook",
        "-i", "localhost,",
        "-c", "local",
        *extra_var_args,
        f"/playbook/{cfg.playbook}",
    ]


def _run_playbook(c: Container, cfg: SandboxConfig) -> int:
    """Run the playbook once, return exit code."""
    result = c.exec(
        *_ansible_playbook_argv(cfg),
        workdir="/playbook",
        check=False,
    )
    return result.returncode


def _check_idempotence(c: Container, cfg: SandboxConfig) -> int:
    """Re-run playbook; succeed iff `changed=0` on every host."""
    print()
    print("=" * 60)
    print(" IDEMPOTENCE CHECK  (second run)")
    print("=" * 60)
    result = c.exec(
        *_ansible_playbook_argv(cfg),
        workdir="/playbook",
        check=False,
        capture_output=True,
    )
    rc = result.returncode
    out = (result.stdout or "") + (result.stderr or "")
    if rc != 0:
        print(f"  FAIL - second run exited with code {rc}")
        for line in out.splitlines()[-20:]:
            print(f"  {line}")
        return 1
    # any task that says `changed=<non-zero>` fails idempotence
    bad = [line for line in out.splitlines() if "changed=" in line and "changed=0" not in line]
    if bad:
        print("  FAIL - tasks still report changes on second run:")
        for line in bad:
            print(f"  {line}")
        # List task names that flipped to `changed` on this run. Ansible
        # prints `TASK [name]` then `changed: [host]` for each non-idempotent
        # task; we pair them up so the user can grep the role and fix.
        print()
        print("  --- non-idempotent tasks (changed on 2nd run) ---")
        current_task: str | None = None
        seen: set[str] = set()
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("TASK ["):
                current_task = s
            elif s.startswith("changed:") and current_task and current_task not in seen:
                seen.add(current_task)
                print(f"  {current_task}")
        return 1
    print("  OK")
    return 0


# =============================================================================
# Config discovery
# =============================================================================

def _discover_configs() -> dict[str, SandboxConfig]:
    """Import every <name>.py under configs/ (plus SANDBOX_CONFIGS_EXTRA_DIR)."""
    dirs: list[Path] = [SANDBOX_DIR / "configs"]
    extra = os.environ.get("SANDBOX_CONFIGS_EXTRA_DIR")
    if extra:
        dirs.append(Path(extra))
    out: dict[str, SandboxConfig] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(f"sandbox_config_{f.stem}", f)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            cfg = getattr(mod, "CONFIG", None)
            if not isinstance(cfg, SandboxConfig):
                continue
            if cfg.name in out:
                print(f"WARNING: config `{cfg.name}` defined twice; later wins.", file=sys.stderr)
            out[cfg.name] = cfg
    return out


# =============================================================================
# Orchestrator
# =============================================================================

def run_sandbox(
    cfg: SandboxConfig,
    runtime: str | None,
    startup_timeout: int = 90,
    keep_container_on_exit: bool = False,
) -> int:
    cfg.pre_flight(PROJECT_DIR)
    rc_total = 0
    with Container(
        runtime=runtime,
        startup_timeout=startup_timeout,
        keep_container_on_exit=keep_container_on_exit,
    ) as c:
        # 1. extra packages
        if cfg.extra_packages_apt:
            print(f"==> Installing extra packages: {' '.join(cfg.extra_packages_apt)}")
            c.exec(
                "apt-get", "update", "-qq",
                user="root",
            )
            c.exec(
                "apt-get", "install", "-y", "--no-install-recommends",
                *cfg.extra_packages_apt,
                user="root",
            )

        # 2. dummy commands
        for src in cfg.dummy_commands:
            print(f"==> Installing dummy command `{src.name}`...")
            c.cp_to(src, f"/usr/local/bin/{src.name}")
            c.exec("chmod", "+x", f"/usr/local/bin/{src.name}", user="root")

        # 3. extra files
        for host_src, container_dst in cfg.extra_files.items():
            if not host_src.exists():
                print(f"==> Skipping extra_file `{host_src}` (not found on host).")
                continue
            print(f"==> Copying `{host_src}` -> `{container_dst}`...")
            parent = os.path.dirname(container_dst)
            if parent:
                c.exec("mkdir", "-p", parent, user="root")
            c.cp_to(host_src, container_dst)
            c.exec(
                "chown", "-R", f"{SANDBOX_USER}:{SANDBOX_USER}", container_dst,
                user="root",
            )

        # 4. post-setup commands (as root). Used to patch up service files etc.
        # that the packages installed in step 1 wrote out. Runs before the
        # project copy so that any systemctl daemon-reload here happens before
        # the playbook's handlers fire.
        for cmd in cfg.post_setup_commands:
            print(f"==> Post-setup: {' '.join(cmd)}")
            c.exec(*cmd, user="root")

        # 5. copy project
        print("==> Copying project into container...")
        c.cp_to(PROJECT_DIR, "/playbook")
        c.exec("chown", "-R", f"{SANDBOX_USER}:{SANDBOX_USER}", "/playbook", user="root")

        # 6. snapshot before
        with tempfile.TemporaryDirectory() as td:
            td_p = Path(td)
            before_tar = td_p / "before.tgz"
            after_tar = td_p / "after.tgz"
            before_dir = td_p / "before"
            after_dir = td_p / "after"

            print("==> Snapshotting before-state...")
            _snapshot(c, cfg.snapshot_paths, before_tar)

            # 7. run playbook
            print()
            print(f"==> Running playbook `{cfg.playbook}` as `{SANDBOX_USER}` (full output follows)...")
            print("-" * 60)
            playbook_rc = _run_playbook(c, cfg)
            print("-" * 60)
            if playbook_rc != 0:
                print(f"WARNING: playbook exited with code {playbook_rc}")
                rc_total += 1

            # 8. snapshot after
            print("==> Snapshotting after-state...")
            _snapshot(c, cfg.snapshot_paths, after_tar)

            # 9. diff
            _extract(before_tar, before_dir)
            _extract(after_tar, after_dir)
            _print_diff(before_dir, after_dir)

            # 10. idempotence
            rc_total += _check_idempotence(c, cfg)

            # 11. post_check
            if cfg.post_check is not None:
                print()
                print("=" * 60)
                print(" POST-CHECK")
                print("=" * 60)
                errors = cfg.post_check(PROJECT_DIR, c)
                if errors:
                    print(f"  FAIL - {errors} error(s)")
                    rc_total += errors
                else:
                    print("  OK")

    return rc_total


# =============================================================================
# CLI
# =============================================================================

def _build_help_epilog(configs: dict[str, SandboxConfig]) -> str:
    if not configs:
        return "\n(no configs discovered)\n"
    lines = ["", "Available configs:"]
    for name in sorted(configs):
        lines.append(f"  {name:20s} {configs[name].description}")
    return "\n".join(lines) + "\n"


def main() -> int:
    configs = _discover_configs()
    ap = argparse.ArgumentParser(
        prog="sandbox.py",
        description=__doc__.splitlines()[0] if __doc__ else "",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_build_help_epilog(configs),
    )
    ap.add_argument("config", choices=sorted(configs), help="config name (see below)")
    ap.add_argument(
        "--runtime",
        choices=["crun", "runc", "system"],
        default="crun",
        help=(
            "OCI runtime for `podman run --runtime <X>`. "
            "'system' = omit the flag entirely (use whatever podman has configured as default). "
            "Note: krun is intentionally absent - libkrun is incompatible with systemd-as-PID-1; "
            "see scripts/sandbox/Dockerfile for rationale. (default: crun)"
        ),
    )
    ap.add_argument(
        "--startup-timeout",
        type=int,
        default=90,
        help="Seconds to wait for systemd inside the container to finish booting before giving up. (default: 90)",
    )
    ap.add_argument(
        "--keep-container-on-exit",
        action="store_true",
        help="Leave the sandbox container running after sandbox.py exits (manual `podman rm -f` afterwards). For debugging.",
    )
    args = ap.parse_args()
    runtime = None if args.runtime == "system" else args.runtime
    return run_sandbox(
        configs[args.config],
        runtime=runtime,
        startup_timeout=args.startup_timeout,
        keep_container_on_exit=args.keep_container_on_exit,
    )


if __name__ == "__main__":
    sys.exit(main())
