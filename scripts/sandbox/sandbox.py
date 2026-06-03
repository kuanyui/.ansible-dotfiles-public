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
import atexit
import importlib.util
import json
import os
import shlex
import signal
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

# Redirect podman's storage root to /tmp so image cache AND every container's
# overlay (where apt install writes deb extracts) live in tmpfs (RAM), not on
# SSD. Repeated sandbox runs no longer pile writes onto disk. Trade-off:
# tmpfs is wiped on reboot, so first sandbox run after each boot rebuilds the
# base image (~1-2 min on a warm apt cache). Acceptable for a dev / test
# tool. Caveat: if your distro bind-mounts /tmp to disk instead of tmpfs
# (uncommon - systemd's default `tmp.mount` is tmpfs), this still works but
# gives no SSD savings; check with `findmnt /tmp`.
PODMAN_STORAGE_ROOT = "/tmp/ansible-dotfiles-sandbox-storage"
PODMAN_STORAGE_RUN = "/tmp/ansible-dotfiles-sandbox-run"


def _podman(*args: str) -> list[str]:
    """Build a `podman ...` argv with `--root` / `--runroot` pinned to tmpfs
    so every podman invocation in this script sees the same storage view."""
    return ["podman", "--root", PODMAN_STORAGE_ROOT, "--runroot", PODMAN_STORAGE_RUN, *args]

# Top-level dirs the before/after snapshot covers. Wide on purpose: roles can
# legitimately write to any of these, and a role accidentally writing to an
# unexpected path (typo in `dest:`, miscomputed `target_home`, etc.) MUST show
# up in the diff so we catch it. Anything outside this list is treated as
# "OS / apt / kernel" territory and not the role's responsibility.
SNAPSHOT_INCLUDES = ["/etc", "/home", "/root", "/usr", "/opt", "/srv", "/var"]

# Within those includes, skip noise that changes every run because of external
# machinery (apt, dpkg, systemd, ansible's caches, log timestamps). These would
# drown actual role-managed writes in the diff. The list is exhaustive on
# purpose - it's cheaper to add one entry here than to chase a phantom diff
# across N sandbox runs.
SNAPSHOT_EXCLUDES = [
    # apt / dpkg state (we don't care about installed-packages bookkeeping)
    "/var/cache/apt/*",
    "/var/lib/apt/*",
    "/var/lib/dpkg/*",
    # man-db cache (auto-rebuilt by apt triggers)
    "/var/lib/man-db/*",
    # systemd runtime state + dbus + nscd + udev
    "/var/lib/systemd/*",
    "/var/lib/dbus/*",
    "/var/lib/nscd/*",
    "/var/lib/udev/*",
    # log files (timestamps change every run)
    "/var/log/*",
    # /var/{tmp,run,lock} are runtime, not config
    "/var/tmp/*",
    "/var/run",
    "/var/lock",
    # dpkg's pwd/group backup files + lock + auto-rebuilt ld cache
    "/etc/passwd-",
    "/etc/group-",
    "/etc/shadow-",
    "/etc/gshadow-",
    "/etc/.pwd.lock",
    "/etc/ld.so.cache",
    # update-alternatives state
    "/etc/alternatives/*",
    # dpkg's own config
    "/etc/dpkg/*",
    # systemd service-enable symlinks created by apt install triggers
    "/etc/systemd/system/multi-user.target.wants/*",
    "/etc/systemd/system/sysinit.target.wants/*",
    "/etc/systemd/system/timers.target.wants/*",
    "/etc/systemd/system/getty.target.wants/*",
    "/etc/systemd/system/sockets.target.wants/*",
    "/etc/systemd/system/network-online.target.wants/*",
    # Ansible's own caches inside the container
    "/home/sandboxuser/.ansible/*",
    "/home/sandboxuser/.ansible_async/*",
    "/root/.ansible/*",
    "/root/.ansible_async/*",
]


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
        self._cleaned_up = False
        self._build_image()
        self._run()
        # Container exists from this point. `with` only calls __exit__ once
        # __enter__ returns successfully, so cleanup during _wait_systemd_ready
        # (or any abnormal interpreter exit afterwards) needs explicit hooks:
        #   - atexit: runs on normal exit + KeyboardInterrupt that bubbles up
        #     + sys.exit(). Does NOT run on uncaught signals like SIGTERM, so
        #     main() installs a SIGTERM->sys.exit handler to route through it.
        #   - try/except below: catches Ctrl+C / errors during the boot wait
        #     while __enter__ hasn't returned yet (so __exit__ wouldn't fire).
        # SIGKILL is unrecoverable by design; document, don't try to handle.
        atexit.register(self._cleanup)
        try:
            self._wait_systemd_ready(timeout=self._startup_timeout)
        except BaseException:
            self._cleanup()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        """Idempotent `podman rm -f`. Honors `_leave_running` for debugging."""
        if self._cleaned_up or self._leave_running:
            return
        self._cleaned_up = True
        self._remove()

    def _build_image(self) -> None:
        print(f"==> Building sandbox image `{IMAGE_TAG}`...")
        subprocess.run(
            _podman("build", "--tag", IMAGE_TAG, str(SANDBOX_DIR)),
            check=True,
        )

    def _run(self) -> None:
        print(
            f"==> Starting container `{self.name}` "
            f"(runtime={self.runtime or 'system-default'})..."
        )
        cmd = _podman(
            "run",
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
        )
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
        subprocess.run(_podman("logs", "--tail", "100", self.name), check=False)
        print(
            f"\nContainer left running for inspection. To clean up:\n"
            f"  podman rm -f {self.name}\n",
            file=sys.stderr,
        )
        self._leave_running = True
        raise SystemExit(1)

    def _remove(self) -> None:
        subprocess.run(
            _podman("rm", "-f", self.name),
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
        podman_cmd = _podman("exec", "--user", user)
        if workdir:
            podman_cmd += ["--workdir", workdir]
        podman_cmd.append(self.name)
        podman_cmd.extend(cmd)
        return subprocess.run(
            podman_cmd, check=check, capture_output=capture_output, text=True,
        )

    def cp_to(self, src: Path, container_dst: str) -> None:
        subprocess.run(
            _podman("cp", str(src), f"{self.name}:{container_dst}"),
            check=True,
        )

    def cp_from(self, container_src: str, dst: Path) -> None:
        subprocess.run(
            _podman("cp", f"{self.name}:{container_src}", str(dst)),
            check=True,
        )


# =============================================================================
# Helpers
# =============================================================================

def _snapshot(c: Container, dst_host_file: Path) -> None:
    """Tar the role-relevant subset of the container's rootfs into a file on
    the host. The include / exclude lists are module-level (SNAPSHOT_INCLUDES,
    SNAPSHOT_EXCLUDES) so the audit scope is identical across every config -
    no per-config snapshot_paths to forget to update when a role changes."""
    remote_tar = f"/tmp/snap-{os.getpid()}.tgz"
    cmd = ["tar", "--ignore-failed-read"]
    for pat in SNAPSHOT_EXCLUDES:
        cmd.extend(["--exclude", pat])
    # `--ignore-failed-read` lets tar warn-then-continue on include paths that
    # don't exist yet (typical for the "before" snapshot when a role hasn't
    # run) and still exit 0.
    cmd.extend(["-czf", remote_tar, *SNAPSHOT_INCLUDES])
    c.exec(*cmd, user="root")
    c.cp_from(remote_tar, dst_host_file)
    c.exec("rm", "-f", remote_tar, user="root")


def _extract(tar_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if tar_path.stat().st_size == 0:
        return
    with tarfile.open(tar_path, "r:gz") as t:
        t.extractall(out_dir)


def _is_empty_tree(p: Path) -> bool:
    """True iff `p` is a directory containing no files or symlinks anywhere
    in its subtree (empty subdirs at most). Used to ignore benign 'Only in'
    leftovers during round-trip: standard XDG dirs (`~/.local/`) and ansible's
    own cache (`~/.ansible/`, content excluded from the snapshot via
    SNAPSHOT_EXCLUDES but the dir itself remains) bottom out as file-less
    subtrees - they're not the role's responsibility to clean up."""
    if not p.is_dir():
        return False
    for child in p.rglob("*"):
        if child.is_file() or child.is_symlink():
            return False
    return True


def _is_benign_only_in(line: str) -> bool:
    """True for `diff -rq` / `diff -ruN` 'Only in <parent>: <name>' lines
    whose target is a file-less subtree (see `_is_empty_tree`)."""
    if not (line.startswith("Only in ") and ": " in line):
        return False
    parent_dir, name = line[len("Only in "):].rsplit(": ", 1)
    return _is_empty_tree(Path(f"{parent_dir}/{name}"))


def _print_diff(before: Path, after: Path, ignore_empty_dir_leftovers: bool = False) -> None:
    print()
    print("=" * 60)
    print(" SANDBOX DIFF  (before -> after)")
    print("=" * 60)
    # `--no-dereference`: compare symlinks by their target-string, not by
    # following them. Snapshots store absolute-target symlinks (e.g. cert hash
    # links `/etc/ssl/certs/X.0 -> /usr/share/ca-certificates/.../X.crt`) as-is.
    # On extraction the absolute target resolves against the HOST root, not
    # the extraction dir - which on a non-Debian host yields ENOENT for every
    # Debian-path symlink and breaks the diff. Comparing by symlink-text
    # sidesteps this entirely; identical symlinks compare equal.
    diff_out = subprocess.run(
        ["diff", "-ruN", "--no-dereference", str(before), str(after)],
        capture_output=True, text=True,
    ).stdout
    # Round-trip caller asks us to suppress 'Only in' entries that point at
    # file-less subtrees (~/.local, ~/.ansible). Pre-filter so neither the
    # raw diff body nor the CHANGED FILES classification below picks them up.
    if ignore_empty_dir_leftovers:
        diff_out = "\n".join(
            ln for ln in diff_out.splitlines() if not _is_benign_only_in(ln)
        )
    # Strip the temp-dir prefixes so paths read as a/etc/... b/etc/...
    diff_out = (
        diff_out
        .replace(f"--- {before}/", "--- a/")
        .replace(f"+++ {after}/", "+++ b/")
        .replace(f"--- {before}", "--- a/")
        .replace(f"+++ {after}", "+++ b/")
    )
    # Color the unified diff in pure Python so we don't depend on `delta` or
    # `grep --color=always` (BSD grep doesn't accept --color=always identically;
    # `delta` is also not always installed). Headers (--- / +++) checked before
    # +/- so their leading dashes/pluses don't get misclassified as deletions/
    # additions.
    GREEN, RED, CYAN, BOLD, RESET = (
        "\033[32m", "\033[31m", "\033[36m", "\033[1m", "\033[0m",
    )
    for line in diff_out.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            print(f"{BOLD}{line}{RESET}")
        elif line.startswith("@@"):
            print(f"{CYAN}{line}{RESET}")
        elif line.startswith("+"):
            print(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"{RED}{line}{RESET}")
        else:
            print(line)
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
    before_str, after_str = str(before), str(after)
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
        elif line.startswith("Only in ") and ": " in line:
            # `diff -ruN` falls back to `Only in <parent>: <name>` for paths
            # that exist on one side and aren't a comparable file (most often
            # empty directories - the unified-diff branch above doesn't fire
            # because there's no file content to render). Translate to the
            # same +/- classification so empty-dir leftovers from a partial
            # unapply still show up in CHANGED FILES.
            rest = line[len("Only in "):]
            parent_dir, name = rest.rsplit(": ", 1)
            full = f"{parent_dir}/{name}"
            if full.startswith(before_str + "/"):
                classified[full[len(before_str) + 1:]] = "-"
            elif full.startswith(after_str + "/"):
                classified[full[len(after_str) + 1:]] = "+"
            i += 1
        else:
            i += 1
    color_map = {"+": GREEN, "-": RED, "=": YELLOW}
    for rel in sorted(classified):
        sym = classified[rel]
        print(f"  {color_map[sym]}{sym} /{rel}{RESET}")


def _ansible_playbook_argv_for(playbook: Path, ansible_vars: dict[str, Any]) -> list[str]:
    # Sandbox is a headless throwaway container - no display server, no point
    # pulling in GTK/Qt deps. Set `has_gui_support=false` globally so roles
    # that branch on it pick the lighter variant (e.g. `emacs-nox` instead of
    # `emacs-gtk` saves ~400 MB of apt install). Caller's vars merged on top,
    # so a config's `extra_ansible_vars` / `unapply_ansible_vars` can override.
    #
    # We pass extra vars as a single `-e <JSON>` instead of repeated
    # `-e key=value` because ansible-core 2.19+ enforces strict types on
    # `when:` conditionals: `-e key=false` is parsed as the STRING `"false"`
    # (which is truthy! - and also rejected as a non-bool conditional in 2.19+),
    # while `-e '{"key": false}'` is parsed as the boolean `False`.
    merged_vars = {"has_gui_support": False, **ansible_vars}
    # Use the project's own `inventory.ini` (not `-i localhost,`) so ansible
    # discovers `group_vars/all.yml` via the inventory-dir lookup. An inline
    # `localhost,` inventory has no inventory-dir and no group_vars get loaded,
    # so any role that gates on `setup_*` / `distro_packages_install_*` defaults
    # would crash with `'<var>' is undefined`. `ansible_connection=local` is
    # set per-host in inventory.ini, so `-c local` is redundant.
    return [
        "ansible-playbook",
        "-i", "/playbook/inventory.ini",
        "-e", json.dumps(merged_vars),
        f"/playbook/{playbook}",
    ]


def _ansible_playbook_argv(cfg: SandboxConfig) -> list[str]:
    """argv for the config's apply playbook."""
    return _ansible_playbook_argv_for(cfg.playbook, cfg.extra_ansible_vars)


def _run_playbook(c: Container, argv: list[str]) -> int:
    """Run the given playbook argv once, return exit code."""
    result = c.exec(*argv, workdir="/playbook", check=False)
    return result.returncode


def _check_idempotence(c: Container, argv: list[str], label: str = "IDEMPOTENCE CHECK  (second run)") -> int:
    """Re-run a playbook argv; succeed iff `changed=0` on every host."""
    print()
    print("=" * 60)
    print(f" {label}")
    print("=" * 60)
    result = c.exec(*argv, workdir="/playbook", check=False, capture_output=True)
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
        # 1. extra packages. Recommends are INCLUDED to match `ansible.builtin.apt`
        # / `ansible.builtin.package` default (`install_recommends=null` ->
        # apt config default -> Debian default true). If we pre-install with
        # `--no-install-recommends` and the playbook later installs the same
        # package via ansible's apt module, ansible would add the missing
        # recommends and those would show up as noise in the before/after diff.
        if cfg.extra_packages_apt:
            print(f"==> Installing extra packages: {' '.join(cfg.extra_packages_apt)}")
            c.exec(
                "apt-get", "update", "-qq",
                user="root",
            )
            c.exec(
                "apt-get", "install", "-y",
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
            _snapshot(c, before_tar)

            # 7. run playbook
            apply_argv = _ansible_playbook_argv(cfg)
            print()
            print(f"==> Running playbook `{cfg.playbook}` as `{SANDBOX_USER}` (full output follows)...")
            print("-" * 60)
            playbook_rc = _run_playbook(c, apply_argv)
            print("-" * 60)
            if playbook_rc != 0:
                print(f"WARNING: playbook exited with code {playbook_rc}")
                rc_total += 1

            # 8. snapshot after
            print("==> Snapshotting after-state...")
            _snapshot(c, after_tar)

            # 9. diff
            _extract(before_tar, before_dir)
            _extract(after_tar, after_dir)
            _print_diff(before_dir, after_dir)

            # 10. idempotence
            rc_total += _check_idempotence(c, apply_argv)

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

            # 12. (optional) round-trip: unapply -> compare against baseline.
            # Strictly additive: rc_total accumulates separately, never folds
            # back into the apply/idempotence/post-check verdicts above. If
            # this section is skipped (cfg.unapply_playbook is None), the
            # sandbox behaves identically to before this feature existed.
            if cfg.unapply_playbook is not None:
                rc_total += _run_round_trip(
                    c, cfg, before_tar, before_dir, td_p,
                )

    return rc_total


def _run_round_trip(
    c: Container,
    cfg: SandboxConfig,
    before_tar: Path,
    before_dir: Path,
    td_p: Path,
) -> int:
    """Run the unapply playbook, snapshot, diff vs the pre-apply baseline, and
    re-run unapply to verify its idempotence. Returns count of errors found;
    callers add to their own rc_total. Does NOT mutate or revisit any verdict
    from earlier in the sandbox run."""
    assert cfg.unapply_playbook is not None
    rc = 0
    unapply_argv = _ansible_playbook_argv_for(cfg.unapply_playbook, cfg.unapply_ansible_vars)

    print()
    print("=" * 60)
    print(" ROUND-TRIP: UNAPPLY")
    print("=" * 60)
    print(f"==> Running unapply playbook `{cfg.unapply_playbook}` as `{SANDBOX_USER}`...")
    print("-" * 60)
    unapply_rc = _run_playbook(c, unapply_argv)
    print("-" * 60)
    if unapply_rc != 0:
        print(f"WARNING: unapply playbook exited with code {unapply_rc}")
        rc += 1

    # Snapshot post-unapply and diff against the pre-apply baseline. A clean
    # uninstall path means these two states match byte-for-byte.
    print("==> Snapshotting post-unapply state...")
    post_unapply_tar = td_p / "post_unapply.tgz"
    post_unapply_dir = td_p / "post_unapply"
    _snapshot(c, post_unapply_tar)
    _extract(post_unapply_tar, post_unapply_dir)

    print()
    print("=" * 60)
    print(" ROUND-TRIP DIFF  (pre-apply baseline vs post-unapply)")
    print(" Any entry below = unapply path left something behind.")
    print(" (Empty XDG / framework dirs like ~/.local, ~/.ansible are")
    print("  filtered - the role isn't expected to clean those up.)")
    print("=" * 60)
    _print_diff(before_dir, post_unapply_dir, ignore_empty_dir_leftovers=True)

    # `diff -rq` returns 0 iff trees are identical (no stdout). Use it as
    # the verdict source because _print_diff's job is display, not pass/fail.
    # Filter the same benign empty-dir leftovers as the display path.
    diff_check = subprocess.run(
        ["diff", "-rq", "--no-dereference", str(before_dir), str(post_unapply_dir)],
        capture_output=True, text=True, check=False,
    )
    real_leftover = [
        ln for ln in diff_check.stdout.strip().splitlines()
        if not _is_benign_only_in(ln)
    ]
    if real_leftover or diff_check.returncode not in (0, 1):
        print(f"  ROUND-TRIP FAIL - {len(real_leftover)} entry/entries not restored to baseline:")
        # Show raw `diff -rq` lines verbatim (`Only in ...: name` and
        # `Files X and Y differ`). Strip the tmpdir prefix so the path reads
        # as the container-absolute path the user actually cares about.
        for ln in real_leftover:
            cleaned = ln.replace(str(before_dir), "<baseline>").replace(str(post_unapply_dir), "<post-unapply>")
            print(f"    {cleaned}")
        # rc >= 2 from `diff -rq` means diff itself failed (unreadable file,
        # broken symlink, etc.) - not a content mismatch. Surface rc + stderr
        # so it's distinguishable from a real "files weren't cleaned up" fail.
        if diff_check.returncode not in (0, 1):
            print(f"  (diff -rq exited rc={diff_check.returncode}; stderr below)")
            stderr_lines = diff_check.stderr.strip().splitlines() or ["(empty)"]
            for ln in stderr_lines:
                print(f"    {ln}")
        rc += 1
    else:
        print("  ROUND-TRIP OK - filesystem matches pre-apply baseline.")

    # Idempotence of unapply itself: re-running uninstall on already-uninstalled
    # state should be a no-op.
    rc += _check_idempotence(
        c, unapply_argv,
        label="UNAPPLY IDEMPOTENCE CHECK  (second unapply run)",
    )
    return rc


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
    # SIGTERM by default kills Python without raising, so atexit-registered
    # container cleanup would not run. Convert it to a sys.exit() so the same
    # cleanup path as a clean exit applies. (SIGINT already raises
    # KeyboardInterrupt by default - no conversion needed.) SIGKILL is
    # unrecoverable: the container will leak. Manual cleanup:
    #   podman ps -a --filter name=ansible-sandbox- --format '{{.ID}}' | xargs -r podman rm -f
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
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
