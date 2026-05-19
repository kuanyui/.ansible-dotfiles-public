#!/usr/bin/env python3
"""Dry-run any project playbook in a throwaway podman + systemd + sshd sandbox.

Runs the playbook against an isolated Debian container (default `--runtime krun`
for microVM isolation), captures a before/after file-tree diff of paths the
playbook touches, runs the playbook again to check idempotence, and invokes
any config-specific post-check (e.g. apparmor_parser --skip-kernel-load for
apparmor profile syntax).

Usage:
    python3 scripts/sandbox/sandbox.py --help
    python3 scripts/sandbox/sandbox.py <config>
    python3 scripts/sandbox/sandbox.py apparmor
    python3 scripts/sandbox/sandbox.py user --runtime crun
    python3 scripts/sandbox/sandbox.py root --runtime default

Configs live in scripts/sandbox/configs/<name>.py with a module-level
`CONFIG = SandboxConfig(...)`. Private overlays can add configs via the
`SANDBOX_CONFIGS_EXTRA_DIR` env var.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Iterable

# Allow `from config import SandboxConfig` when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SandboxConfig  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parents[2]
SANDBOX_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE = "debian:trixie"
SANDBOX_USER = "sandboxuser"
CACHE_DIR = Path.home() / ".cache" / "ansible-dotfiles-sandbox"
SSH_KEY = CACHE_DIR / "ssh_key"
IMAGE_TAG = "localhost/ansible-dotfiles-sandbox:latest"


# =============================================================================
# Container handle
# =============================================================================

class Container:
    """RAII wrapper for the podman lifecycle: build image, run, ssh, cleanup."""

    def __init__(self, runtime: str | None) -> None:
        # runtime: "krun" | "crun" | None (None = don't pass --runtime to podman)
        self.runtime = runtime
        self.name = f"ansible-sandbox-{os.getpid()}"
        self._ssh_port: int | None = None

    # ---------- lifecycle ----------

    def __enter__(self) -> "Container":
        _ensure_ssh_key()
        self._build_image()
        self._run()
        self._wait_ssh_ready(timeout=60)
        return self

    def __exit__(self, *exc: object) -> None:
        self._remove()

    def _build_image(self) -> None:
        print(f"==> Building sandbox image `{IMAGE_TAG}`...")
        pubkey = (SSH_KEY.with_suffix(".pub")).read_text().strip()
        subprocess.run(
            [
                "podman", "build",
                "--tag", IMAGE_TAG,
                "--build-arg", f"SSH_AUTHORIZED_KEY={pubkey}",
                str(SANDBOX_DIR),
            ],
            check=True,
        )

    def _run(self) -> None:
        print(f"==> Starting container `{self.name}` (runtime={self.runtime or 'default'})...")
        cmd = [
            "podman", "run",
            "--name", self.name,
            "--detach",
            "--systemd=always",
            "--publish", "0:22",
        ]
        if self.runtime:
            cmd += ["--runtime", self.runtime]
        cmd.append(IMAGE_TAG)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    def _wait_ssh_ready(self, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.ssh("true", check=True, capture_output=True, _retry=False)
                print("==> sshd ready.")
                return
            except subprocess.CalledProcessError:
                time.sleep(1)
        raise SystemExit(f"sshd inside `{self.name}` not reachable within {timeout}s")

    def _remove(self) -> None:
        subprocess.run(
            ["podman", "rm", "-f", self.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )

    # ---------- ssh / cp ----------

    @property
    def ssh_port(self) -> int:
        if self._ssh_port is None:
            out = subprocess.run(
                ["podman", "port", self.name, "22"],
                check=True, capture_output=True, text=True,
            ).stdout.strip().splitlines()
            # output looks like "0.0.0.0:43217" or "127.0.0.1:43217"
            self._ssh_port = int(out[0].rsplit(":", 1)[1])
        return self._ssh_port

    def ssh(
        self,
        *cmd: str,
        user: str = SANDBOX_USER,
        check: bool = True,
        capture_output: bool = False,
        _retry: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a remote command via ssh. Pass cmd as separate args (no shell)."""
        ssh_cmd = [
            "ssh",
            "-p", str(self.ssh_port),
            "-i", str(SSH_KEY),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=5",
            f"{user}@127.0.0.1",
            *cmd,
        ]
        return subprocess.run(ssh_cmd, check=check, capture_output=capture_output, text=True)

    def cp_to(self, src: Path, container_dst: str, *, become_root: bool = False) -> None:
        """Copy host path into container."""
        target_for_podman_cp = f"{self.name}:{container_dst}"
        subprocess.run(["podman", "cp", str(src), target_for_podman_cp], check=True)
        if become_root:
            self.ssh("sudo", "chown", "-R", "root:root", container_dst)

    def cp_from(self, container_src: str, dst: Path) -> None:
        subprocess.run(["podman", "cp", f"{self.name}:{container_src}", str(dst)], check=True)


# =============================================================================
# Helpers
# =============================================================================

def _ensure_ssh_key() -> None:
    if SSH_KEY.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ssh-keygen", "-t", "ed25519", "-N", "",
            "-f", str(SSH_KEY),
            "-C", f"ansible-dotfiles-sandbox client key (host {os.uname().nodename})",
        ],
        check=True, stdout=subprocess.DEVNULL,
    )
    print(f"==> Generated sandbox SSH key at {SSH_KEY}.")


def _snapshot(c: Container, paths: list[str], dst_host_file: Path) -> None:
    """Tar listed container paths into a file on the host."""
    if not paths:
        dst_host_file.write_bytes(b"")
        return
    remote_tar = f"/tmp/snap-{os.getpid()}.tgz"
    # tar exits non-zero if a listed path doesn't exist; suppress so a path that
    # the playbook will create still works for "before" snapshot.
    c.ssh("sudo", "bash", "-c", f"tar -czf {remote_tar} {' '.join(paths)} 2>/dev/null || true")
    c.cp_from(remote_tar, dst_host_file)
    c.ssh("sudo", "rm", "-f", remote_tar)


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
    # Summary of changed files
    print()
    print("-" * 60)
    print(" CHANGED FILES")
    print("-" * 60)
    changed: set[str] = set()
    for line in diff_out.splitlines():
        if line.startswith("--- a/") or line.startswith("+++ b/"):
            p = line.split("\t", 1)[0].split(" ", 1)[1][2:]
            if p and p != "/dev/null":
                changed.add(p)
    for p in sorted(changed):
        print(f"  {p}")


def _run_playbook(c: Container, cfg: SandboxConfig) -> int:
    """Run the playbook once, return exit code."""
    extra_var_args: list[str] = []
    for k, v in cfg.extra_ansible_vars.items():
        extra_var_args += ["-e", f"{k}={v}"]
    cmd = [
        "cd", "/playbook", "&&",
        "ansible-playbook", "-i", "localhost,", "-c", "local",
        *extra_var_args,
        f"/playbook/{cfg.playbook}",
    ]
    result = c.ssh("bash", "-c", " ".join(cmd), check=False)
    return result.returncode


def _check_idempotence(c: Container, cfg: SandboxConfig) -> int:
    """Re-run playbook; succeed iff `changed=0` on every host."""
    print()
    print("=" * 60)
    print(" IDEMPOTENCE CHECK  (second run)")
    print("=" * 60)
    extra_var_args: list[str] = []
    for k, v in cfg.extra_ansible_vars.items():
        extra_var_args += ["-e", f"{k}={v}"]
    cmd = [
        "cd", "/playbook", "&&",
        "ansible-playbook", "-i", "localhost,", "-c", "local",
        *extra_var_args,
        f"/playbook/{cfg.playbook}",
    ]
    result = c.ssh("bash", "-c", " ".join(cmd), check=False, capture_output=True)
    rc = result.returncode
    out = (result.stdout or "") + (result.stderr or "")
    if rc != 0:
        print(f"  FAIL - second run exited with code {rc}")
        for line in out.splitlines()[-20:]:
            print(f"  {line}")
        return 1
    # any task that says `changed=<non-zero>` fails idempotence
    bad = [line for line in out.splitlines() if "changed=" in line and not "changed=0" in line]
    if bad:
        print("  FAIL - tasks still report changes on second run:")
        for line in bad:
            print(f"  {line}")
        return 1
    print("  OK")
    return 0


# =============================================================================
# Config discovery
# =============================================================================

def _discover_configs() -> dict[str, SandboxConfig]:
    """Import every <name>.py under configs/ (plus SANDBOX_CONFIGS_EXTRA_DIR) and
    collect their module-level `CONFIG = SandboxConfig(...)` into a name -> cfg map.
    """
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

def run_sandbox(cfg: SandboxConfig, runtime: str | None) -> int:
    cfg.pre_flight(PROJECT_DIR)
    rc_total = 0
    with Container(runtime=runtime) as c:
        # 1. extra packages
        if cfg.extra_packages_apt:
            print(f"==> Installing extra packages: {' '.join(cfg.extra_packages_apt)}")
            c.ssh(
                "sudo", "DEBIAN_FRONTEND=noninteractive",
                "apt-get", "update", "-qq",
            )
            c.ssh(
                "sudo", "DEBIAN_FRONTEND=noninteractive",
                "apt-get", "install", "-y", "--no-install-recommends",
                *cfg.extra_packages_apt,
            )

        # 2. dummy commands
        for src in cfg.dummy_commands:
            print(f"==> Installing dummy command `{src.name}`...")
            c.cp_to(src, f"/usr/local/bin/{src.name}")
            c.ssh("sudo", "chmod", "+x", f"/usr/local/bin/{src.name}")

        # 3. extra files
        for host_src, container_dst in cfg.extra_files.items():
            if not host_src.exists():
                print(f"==> Skipping extra_file `{host_src}` (not found on host).")
                continue
            print(f"==> Copying `{host_src}` -> `{container_dst}`...")
            # ensure parent dir
            parent = os.path.dirname(container_dst)
            if parent:
                c.ssh("mkdir", "-p", parent)
            c.cp_to(host_src, container_dst)
            c.ssh("sudo", "chown", "-R", f"{SANDBOX_USER}:{SANDBOX_USER}", container_dst)

        # 4. copy project
        print("==> Copying project into container...")
        c.cp_to(PROJECT_DIR, "/playbook")
        c.ssh("sudo", "chown", "-R", f"{SANDBOX_USER}:{SANDBOX_USER}", "/playbook")

        # 5. snapshot before
        with tempfile.TemporaryDirectory() as td:
            td_p = Path(td)
            before_tar = td_p / "before.tgz"
            after_tar = td_p / "after.tgz"
            before_dir = td_p / "before"
            after_dir = td_p / "after"

            print("==> Snapshotting before-state...")
            _snapshot(c, cfg.snapshot_paths, before_tar)

            # 6. run playbook
            print()
            print(f"==> Running playbook `{cfg.playbook}` as `{SANDBOX_USER}` (full output follows)...")
            print("-" * 60)
            playbook_rc = _run_playbook(c, cfg)
            print("-" * 60)
            if playbook_rc != 0:
                print(f"WARNING: playbook exited with code {playbook_rc}")
                rc_total += 1

            # 7. snapshot after
            print("==> Snapshotting after-state...")
            _snapshot(c, cfg.snapshot_paths, after_tar)

            # 8. diff
            _extract(before_tar, before_dir)
            _extract(after_tar, after_dir)
            _print_diff(before_dir, after_dir)

            # 9. idempotence
            rc_total += _check_idempotence(c, cfg)

            # 10. post_check
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
        choices=["krun", "crun", "default"],
        default="krun",
        help="OCI runtime for podman run. 'default' = no --runtime flag (system default). (default: krun)",
    )
    args = ap.parse_args()
    runtime = None if args.runtime == "default" else args.runtime
    return run_sandbox(configs[args.config], runtime=runtime)


if __name__ == "__main__":
    sys.exit(main())
