#!/usr/bin/env python3
"""Standalone incus storage-pool inspector / verifier for `roles/incus_vm`.

Phase 1 (this file): READ-ONLY `status` + `verify`. Two callers:
  - ansible, at the END of `make incus-install`: `verify` asserts the LIVE pool
    matches what was requested (loud non-zero exit on mismatch), and `status`
    prints the real mount / fstab / `incus storage list` picture so the user (and
    the playbook log) can see the result.
  - `ivm storage-status`: one command for the whole host storage picture.

Phase 2 (later, on a host-verified baseline): fold the MUTATING build-loop /
init / delete-pool logic - today scattered across `tasks/incus_host_*.yml` as
hard-to-read `shell:`/`when:`/`set_fact:` chains - into this same file as extra
subcommands, so the imperative storage lifecycle lives in ONE readable, testable
place. Every mutating subcommand added then MUST print its exact argv before
running (the project's transparency-before-privileged-actions rule).

stdlib only (the project is ansible-core / no-extra-deps; this mirrors that).
Runs both as root (ansible: full `incus storage show` config) and as an
unprivileged `incus`-group user (`ivm`: pool config is admin-only, so `source`
falls back to the role-recorded `storage-info.json`)."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from typing import Any

FSTAB_PATH: str = "/etc/fstab"
PROC_MOUNTS_PATH: str = "/proc/mounts"
FSTAB_LOOP_OPTIONS: str = "loop,nofail,noatime"


def run_capture(argv: list[str]) -> tuple[int, str, str]:
    """Run `argv`, return `(returncode, stdout, stderr)`; never raises (a missing
    binary -> rc 127). Used for the best-effort `incus ...` probes below."""
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: not found"
    return completed.returncode, completed.stdout, completed.stderr


def human_iec_bytes(num_bytes: int) -> str:
    """A raw byte count -> IEC string with 2 decimals (e.g. 5368709120 -> `5.00GiB`),
    matching the style `incus storage info` prints."""
    size_in_current_unit: float = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if size_in_current_unit < 1024.0 or unit == "PiB":
            return f"{int(size_in_current_unit)}{unit}" if unit == "B" else f"{size_in_current_unit:.2f}{unit}"
        size_in_current_unit /= 1024.0
    return f"{num_bytes}B"  # unreachable; satisfies the type checker


def read_storage_info(root: str) -> dict[str, Any] | None:
    """The role records the REQUESTED layout (driver, the loop `.img` it built,
    mount point, size) to `<root>/storage-info.json` at install. Returns it, or
    None when absent/unreadable (e.g. ansible calls this mid-install, before
    `ivm_install.yml` has written the file)."""
    try:
        parsed: Any = json.loads(open(os.path.join(root, "storage-info.json")).read())
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def live_default_pool() -> dict[str, Any]:
    """The LIVE `default` storage pool as incus reports it: `{present, driver,
    source}`. `driver` comes from `incus storage list` (readable by any
    `incus`-group member); `source` from `incus storage show default`
    (admin-only -> empty string for an unprivileged caller)."""
    present: bool = False
    driver: str = ""
    rc_list, stdout_list, _ = run_capture(["incus", "storage", "list", "--format", "csv"])
    if rc_list == 0:
        for csv_line in stdout_list.splitlines():
            fields: list[str] = csv_line.split(",")
            if fields and fields[0] == "default":
                present = True
                driver = fields[1] if len(fields) > 1 else ""
                break
    source: str = ""
    rc_show, stdout_show, _ = run_capture(["incus", "storage", "show", "default"])
    if rc_show == 0:
        for show_line in stdout_show.splitlines():
            stripped: str = show_line.strip()
            if stripped.startswith("source:"):
                source = stripped.split(":", 1)[1].strip()
                break
    return {"present": present, "driver": driver, "source": source}


def loop_backing_file_of(mount_device: str) -> str:
    """For a loop device (`/dev/loopN`) read its backing file from sysfs
    (world-readable, no `losetup`/root), stripping a trailing ` (deleted)`.
    Non-loop devices return as-is."""
    device_basename: str = os.path.basename(mount_device)
    if not device_basename.startswith("loop"):
        return mount_device
    try:
        backing_file: str = open(f"/sys/block/{device_basename}/loop/backing_file").read().strip()
    except OSError:
        return mount_device
    suffix_for_deleted_backing: str = " (deleted)"
    if backing_file.endswith(suffix_for_deleted_backing):
        backing_file = backing_file[: -len(suffix_for_deleted_backing)]
    return backing_file


def mount_state_of(mountpoint: str) -> dict[str, Any]:
    """Read `/proc/mounts` (always readable) for `mountpoint`: `{mounted, device,
    fstype, backing_file}`. `backing_file` resolves a loop device to its real
    `.img` (with any ` (deleted)` ghost suffix stripped)."""
    if not mountpoint:
        return {"mounted": False, "device": "", "fstype": "", "backing_file": ""}
    try:
        proc_mounts_text: str = open(PROC_MOUNTS_PATH).read()
    except OSError:
        return {"mounted": False, "device": "", "fstype": "", "backing_file": ""}
    for mount_line in proc_mounts_text.splitlines():
        fields: list[str] = mount_line.split()
        if len(fields) < 3:
            continue
        # /proc/mounts escapes spaces in the mountpoint as the octal \040.
        mount_target: str = fields[1].replace("\\040", " ")
        if mount_target == mountpoint:
            mount_device: str = fields[0]
            return {
                "mounted": True,
                "device": mount_device,
                "fstype": fields[2],
                "backing_file": loop_backing_file_of(mount_device),
            }
    return {"mounted": False, "device": "", "fstype": "", "backing_file": ""}


def fstab_line_for(mountpoint: str) -> str:
    """The `/etc/fstab` line whose mount target (2nd field) is `mountpoint`,
    or '' when none (comments skipped)."""
    if not mountpoint:
        return ""
    try:
        fstab_text: str = open(FSTAB_PATH).read()
    except OSError:
        return ""
    for fstab_line in fstab_text.splitlines():
        if fstab_line.lstrip().startswith("#"):
            continue
        fields: list[str] = fstab_line.split()
        if len(fields) >= 2 and fields[1] == mountpoint:
            return fstab_line.strip()
    return ""


def loop_file_footprint(loop_file_path: str) -> dict[str, Any]:
    """A sparse `.img`'s real on-disk use (`st_blocks * 512`, what `du` reports)
    vs its logical/declared size (`st_size`). `{exists, on_disk_bytes,
    logical_bytes}`; `stat` needs only traverse on the parent dirs, not read."""
    try:
        loop_file_stat: os.stat_result = os.stat(loop_file_path)
    except OSError:
        return {"exists": False, "on_disk_bytes": 0, "logical_bytes": 0}
    return {
        "exists": True,
        "on_disk_bytes": loop_file_stat.st_blocks * 512,
        "logical_bytes": loop_file_stat.st_size,
    }


def gather(root: str) -> dict[str, Any]:
    """Assemble the full storage picture: the REQUESTED layout (`storage-info.json`),
    the LIVE pool, and the host-side mount / fstab / loop-file facts that decide
    whether the two agree."""
    recorded: dict[str, Any] | None = read_storage_info(root)
    live: dict[str, Any] = live_default_pool()
    # The loop mount point + the `.img` to inspect come from the recorded config
    # (that is what the role built); fall back to the live pool source for the
    # mount point so `status` still says something useful without a record.
    recorded_mountpoint: str = (recorded or {}).get("mountpoint") or ""
    recorded_loop_file: str = (recorded or {}).get("loop_file") or ""
    mountpoint_to_probe: str = recorded_mountpoint or (live["source"] if live["source"].startswith("/") else "")
    return {
        "recorded": recorded,
        "live_pool": live,
        "mount": mount_state_of(mountpoint_to_probe),
        "mountpoint": mountpoint_to_probe,
        "fstab_line": fstab_line_for(mountpoint_to_probe),
        "loop_file": recorded_loop_file,
        "loop_footprint": loop_file_footprint(recorded_loop_file) if recorded_loop_file else {"exists": False, "on_disk_bytes": 0, "logical_bytes": 0},
        "raw_storage_list": run_capture(["incus", "storage", "list"])[1],
    }


def verdict(data: dict[str, Any]) -> tuple[str, list[str]]:
    """Reduce the gathered picture to a single verdict + reasons:
      `no-pool`    - no `default` pool exists.
      `MISMATCH`   - recorded vs live driver differ, or a recorded loop is not
                     actually mounted from its `.img` (the bugs this guards).
      `consistent` - live pool agrees with the recorded request."""
    live: dict[str, Any] = data["live_pool"]
    recorded: dict[str, Any] | None = data["recorded"]
    if not live["present"]:
        return "no-pool", ["no `default` storage pool exists"]
    reasons: list[str] = []
    if recorded:
        recorded_driver: str = str(recorded.get("driver") or "")
        if recorded_driver and live["driver"] and recorded_driver != live["driver"]:
            reasons.append(f"recorded driver `{recorded_driver}` != live driver `{live['driver']}`"
                           " (an existing pool was never re-pointed; `incus admin init` was skipped)")
        if recorded.get("build_loop") and recorded.get("loop_file"):
            if not data["mount"]["mounted"]:
                reasons.append(f"recorded a btrfs loop but {data['mountpoint']} is NOT mounted")
            elif data["mount"]["backing_file"] != recorded["loop_file"]:
                reasons.append(f"{data['mountpoint']} is mounted from `{data['mount']['backing_file']}`,"
                               f" not the recorded loop `{recorded['loop_file']}` (stale / ghost mount)")
    return ("MISMATCH", reasons) if reasons else ("consistent", [])


def render_text(data: dict[str, Any]) -> str:
    """Human-readable dump: the three things the user asked to see (live
    `incus storage list`, the mount, the fstab line) plus the recorded request
    and the verdict."""
    live: dict[str, Any] = data["live_pool"]
    recorded: dict[str, Any] | None = data["recorded"]
    mount: dict[str, Any] = data["mount"]
    footprint: dict[str, Any] = data["loop_footprint"]
    state, reasons = verdict(data)
    lines: list[str] = ["==== incus storage pool status ===="]
    lines.append("")
    lines.append("-- live `incus storage list` --")
    lines.append((data["raw_storage_list"] or "(incus did not report / not reachable)").rstrip())
    lines.append("")
    lines.append("-- default pool --")
    lines.append(f"  present: {live['present']}")
    lines.append(f"  driver:  {live['driver'] or '(unknown)'}")
    lines.append(f"  source:  {live['source'] or '(empty / admin-only - not readable unprivileged)'}")
    lines.append("")
    lines.append("-- loop mount --")
    lines.append(f"  mountpoint:   {data['mountpoint'] or '(n/a)'}")
    lines.append(f"  mounted:      {mount['mounted']}")
    if mount["mounted"]:
        lines.append(f"  device:       {mount['device']}  (fstype {mount['fstype']})")
        lines.append(f"  backing file: {mount['backing_file']}")
    lines.append(f"  /etc/fstab:   {data['fstab_line'] or '(no line for this mountpoint)'}")
    if data["loop_file"]:
        usage: str = (f"{human_iec_bytes(footprint['on_disk_bytes'])} on disk / "
                      f"{human_iec_bytes(footprint['logical_bytes'])} max") if footprint["exists"] else "(file absent)"
        lines.append(f"  loop file:    {data['loop_file']}  (sparse: {usage})")
    lines.append("")
    lines.append("-- recorded request (storage-info.json) --")
    if recorded is None:
        lines.append("  (none - storage-info.json absent)")
    else:
        for key in ("driver", "build_loop", "loop_file", "mountpoint", "source", "size"):
            if key in recorded:
                lines.append(f"  {key}: {recorded[key]}")
    lines.append("")
    lines.append(f"==== VERDICT: {state} ====")
    for reason in reasons:
        lines.append(f"  - {reason}")
    return "\n".join(lines)


def cmd_status(root: str, as_json: bool) -> int:
    data: dict[str, Any] = gather(root)
    if as_json:
        state, reasons = verdict(data)
        print(json.dumps({**data, "verdict": state, "verdict_reasons": reasons}, indent=2))
    else:
        print(render_text(data))
    return 0


def cmd_verify(root: str, expect_driver: str, expect_source: str,
               expect_loop_backing: str, as_json: bool) -> int:
    """Assert the LIVE pool matches what `incus-install` was asked to build. Hard
    checks (each a non-zero exit): pool exists; driver matches; source matches; and
    when a loop backing is expected, the source mount point is mounted from that
    exact `.img`. Prints the full status first either way."""
    data: dict[str, Any] = gather(root)
    live: dict[str, Any] = data["live_pool"]
    failures: list[str] = []
    if not live["present"]:
        failures.append("no `default` storage pool exists after install")
    if expect_driver and live["driver"] and live["driver"] != expect_driver:
        failures.append(f"driver is `{live['driver']}`, expected `{expect_driver}`")
    if expect_source and live["source"] and live["source"] != expect_source:
        failures.append(f"pool source is `{live['source']}`, expected `{expect_source}`")
    if expect_loop_backing:
        mount_at_source: dict[str, Any] = mount_state_of(expect_source)
        if not mount_at_source["mounted"]:
            failures.append(f"expected loop mount {expect_source} is NOT mounted")
        elif mount_at_source["backing_file"] != expect_loop_backing:
            failures.append(f"{expect_source} is mounted from `{mount_at_source['backing_file']}`,"
                            f" expected the loop `{expect_loop_backing}`")
    if as_json:
        print(json.dumps({"ok": not failures, "failures": failures, **data}, indent=2))
    else:
        print(render_text(data))
        print("")
        if failures:
            print("==== VERIFY FAILED ====")
            for failure in failures:
                print(f"  - {failure}")
            print("\nThe install reported success but the storage pool is NOT what was requested.")
            print("Rebuild: `make incus-teardown-host` then re-run `make incus-install INCUS_STORAGE_POOL_*=...`")
        else:
            print("==== VERIFY OK: live pool matches the requested layout ====")
    return 1 if failures else 0


# ---------- MUTATING subcommands (build-loop / init / delete-pool) ----------
# These replace the imperative truncate/mkfs/fstab/mount + `incus admin init` + pool
# delete chains that used to live as hard-to-read `shell:`/`when:`/`set_fact:` tasks in
# tasks/incus_host_*.yml. ansible now calls them via the `script` module. Each prints
# its exact argv (or the file write) BEFORE acting (the project's
# transparency-before-privileged-actions rule), runs as root, is idempotent, and ends
# with a `RESULT: changed|noop` line that drives ansible's `changed_when`.


def run_privileged(argv: list[str], *, dry_run: bool) -> None:
    """Run a MUTATING command, printing its exact argv FIRST. Raises on non-zero."""
    print("+ " + shlex.join(argv), file=sys.stderr)
    if not dry_run:
        subprocess.run(argv, check=True)


def ensure_loop_file(source: str, size: str, *, dry_run: bool) -> bool:
    """`truncate` a sparse `.img` at `source` if absent, then `mkfs.btrfs` it if it has
    no filesystem yet (never reformats an existing one). Returns True if it changed.
    `size` is the incus form e.g. `100GiB`; `truncate`'s binary `G`/`T` already mean
    GiB/TiB, so we just drop the `iB` (matches the old role's regex)."""
    changed: bool = False
    if not os.path.exists(source):
        run_privileged(["truncate", f"--size={re.sub(r'iB$', '', size)}", source], dry_run=dry_run)
        changed = True
    existing_fs_type: str = run_capture(["blkid", "--output", "value", "--match-tag", "TYPE", source])[1].strip()
    if not existing_fs_type:
        run_privileged(["mkfs.btrfs", source], dry_run=dry_run)
        changed = True
    return changed


def ensure_fstab_loop_line(source: str, mountpoint: str, *, dry_run: bool) -> bool:
    """Ensure exactly one /etc/fstab line loop-mounts `source` at `mountpoint` as btrfs,
    replacing any stale line for that mountpoint (a changed source is corrected in
    place). `nofail` so a missing disk never blocks boot. Returns True if changed."""
    wanted_line: str = f"{source} {mountpoint} btrfs {FSTAB_LOOP_OPTIONS} 0 0"
    try:
        current_lines: list[str] = open(FSTAB_PATH).read().splitlines()
    except OSError:
        current_lines = []
    kept_lines: list[str] = [fstab_line for fstab_line in current_lines
                             if fstab_line.lstrip().startswith("#")
                             or len(fstab_line.split()) < 2
                             or fstab_line.split()[1] != mountpoint]
    new_lines: list[str] = kept_lines + [wanted_line]
    if new_lines == current_lines:
        return False
    print(f"+ write {FSTAB_PATH}: {wanted_line}", file=sys.stderr)
    if not dry_run:
        with open(FSTAB_PATH, "w") as fstab_file:
            fstab_file.write("\n".join(new_lines) + "\n")
    return True


def remove_fstab_line(mountpoint: str, *, dry_run: bool) -> bool:
    """Remove any (non-comment) /etc/fstab line for `mountpoint`. Returns True if changed."""
    try:
        current_lines: list[str] = open(FSTAB_PATH).read().splitlines()
    except OSError:
        return False
    kept_lines: list[str] = [fstab_line for fstab_line in current_lines
                             if fstab_line.lstrip().startswith("#")
                             or len(fstab_line.split()) < 2
                             or fstab_line.split()[1] != mountpoint]
    if kept_lines == current_lines:
        return False
    print(f"+ remove {FSTAB_PATH} line for {mountpoint}", file=sys.stderr)
    if not dry_run:
        with open(FSTAB_PATH, "w") as fstab_file:
            fstab_file.write("\n".join(kept_lines) + ("\n" if kept_lines else ""))
    return True


def ensure_mounted_from_source(source: str, mountpoint: str, *, dry_run: bool) -> bool:
    """Mount `mountpoint` (via its fstab entry) from `source`, REPLACING any stale mount
    whose backing file is not `source` - a leftover loop from a prior pool (possibly
    already `(deleted)`) would otherwise shadow it and the new pool would silently sit on
    the wrong filesystem. Safe: callers run this only first-time, when no `default` pool
    uses the mount yet. Returns True if changed."""
    state: dict[str, Any] = mount_state_of(mountpoint)
    if state["mounted"] and state["backing_file"] == source:
        return False
    if state["mounted"]:
        print(f"+ stale mount at {mountpoint}: backed by {state['backing_file']}, want {source} - replacing",
              file=sys.stderr)
        run_privileged(["umount", mountpoint], dry_run=dry_run)
    run_privileged(["mount", mountpoint], dry_run=dry_run)
    return True


def cmd_build_loop(source: str, size: str, mountpoint: str, *, dry_run: bool) -> int:
    """Build + mount the btrfs loop file the `default` pool lives on - the part incus
    cannot do itself (it only ever makes a loop at /var/lib/incus/disks on `/`). All
    idempotent. Replaces the truncate/mkfs/mkdir/fstab/mount ansible task chain."""
    changed: bool = ensure_loop_file(source, size, dry_run=dry_run)
    if not os.path.isdir(mountpoint):
        run_privileged(["mkdir", "--mode=0711", "--parents", mountpoint], dry_run=dry_run)
        changed = True
    changed = ensure_fstab_loop_line(source, mountpoint, dry_run=dry_run) or changed
    changed = ensure_mounted_from_source(source, mountpoint, dry_run=dry_run) or changed
    print(f"RESULT: {'changed' if changed else 'noop'}")
    return 0


def build_preseed(driver: str, pool_source: str, pool_size: str) -> dict[str, Any]:
    """The `incus admin init --preseed` document: the `default` storage pool (with the
    EFFECTIVE source/size), the `incusbr0` managed bridge, and a `default` profile wiring
    eth0->incusbr0 + root-disk->default pool. Same content the old
    templates/incus_preseed.yml.j2 produced - now one source of truth, in Python."""
    pool: dict[str, Any] = {"name": "default", "driver": driver}
    pool_config: dict[str, str] = {}
    if pool_source:
        pool_config["source"] = pool_source
    if pool_size:
        pool_config["size"] = pool_size
    if pool_config:
        pool["config"] = pool_config
    return {
        "config": {},
        "networks": [{"name": "incusbr0", "type": "bridge",
                      "config": {"ipv4.address": "auto", "ipv6.address": "auto"}}],
        "storage_pools": [pool],
        "profiles": [{"name": "default", "devices": {
            "eth0": {"name": "eth0", "network": "incusbr0", "type": "nic"},
            "root": {"path": "/", "pool": "default", "type": "disk"},
        }}],
        "projects": [],
        "cluster": None,
    }


def cmd_init(driver: str, pool_source: str, pool_size: str, *, dry_run: bool) -> int:
    """First-time `incus admin init --preseed` (storage pool + incusbr0 + default
    profile). No-op if a `default` pool already exists (never re-points one).
    `pool_source`/`pool_size` are the EFFECTIVE values (for a role-built loop: the mount
    point + empty size). The preseed is fed as JSON, which incus parses as YAML."""
    if live_default_pool()["present"]:
        print("RESULT: noop  (a `default` pool already exists - incus admin init skipped)")
        return 0
    preseed_json: str = json.dumps(build_preseed(driver, pool_source, pool_size), indent=2)
    print("+ incus admin init --preseed  with this preseed (JSON is valid YAML):", file=sys.stderr)
    print(preseed_json, file=sys.stderr)
    if not dry_run:
        subprocess.run(["incus", "admin", "init", "--preseed"], input=preseed_json, text=True, check=True)
    print("RESULT: changed")
    return 0


def cmd_delete_pool(mountpoint: str, *, dry_run: bool) -> int:
    """Reverse the storage side of init+build-loop: detach the `default` profile's root
    disk (it pins the pool), delete the `default` pool, then unmount the loop + drop its
    fstab line (the `.img` file is left for reuse). Idempotent. (The incus.service
    mount-wait drop-in removal stays in ansible.)"""
    changed: bool = False
    if "root" in run_capture(["incus", "profile", "device", "list", "default"])[1].split():
        run_privileged(["incus", "profile", "device", "remove", "default", "root"], dry_run=dry_run)
        changed = True
    if live_default_pool()["present"]:
        run_privileged(["incus", "storage", "delete", "default"], dry_run=dry_run)
        changed = True
    if mount_state_of(mountpoint)["mounted"]:
        run_privileged(["umount", mountpoint], dry_run=dry_run)
        changed = True
    changed = remove_fstab_line(mountpoint, dry_run=dry_run) or changed
    print(f"RESULT: {'changed' if changed else 'noop'}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="incus_storage_pool.py",
        description="Inspect / verify / build / delete the incus `default` storage pool.")
    parser.add_argument("--root", default=os.path.expanduser(
        "~/.local/share/ansible-managed/incus-vm/ivm"),
        help="dir holding storage-info.json (the role-recorded REQUESTED layout)")
    parser.add_argument("--json", action="store_true", help="machine-readable output (status / verify)")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # Read-only.
    sub.add_parser("status", help="print the full live storage picture (mount / fstab / incus storage list)")
    verify_parser: argparse.ArgumentParser = sub.add_parser(
        "verify", help="exit non-zero if the live pool does not match the expected layout")
    verify_parser.add_argument("--expect-driver", default="", help="driver the pool should have (e.g. btrfs)")
    verify_parser.add_argument("--expect-source", default="", help="config.source the pool should have")
    verify_parser.add_argument("--expect-loop-backing", default="",
                               help="the `.img` the --expect-source mount point should be mounted from")

    # Mutating (run as root; print argv before acting; idempotent).
    build_loop_parser: argparse.ArgumentParser = sub.add_parser(
        "build-loop", help="truncate + mkfs.btrfs + fstab + source-aware mount the loop `.img` the pool lives on")
    build_loop_parser.add_argument("--source", required=True, help="the `.img` path on the big disk")
    build_loop_parser.add_argument("--size", required=True, help="loop size, incus form (e.g. 100GiB)")
    build_loop_parser.add_argument("--mountpoint", required=True, help="where the loop is mounted (the pool source)")
    build_loop_parser.add_argument("--dry-run", action="store_true", help="print actions without running them")

    init_parser: argparse.ArgumentParser = sub.add_parser(
        "init", help="first-time `incus admin init --preseed` (pool + incusbr0 + default profile); no-op if a pool exists")
    init_parser.add_argument("--driver", required=True, help="pool driver (dir / btrfs / zfs / lvm-thin)")
    init_parser.add_argument("--pool-source", default="", help="EFFECTIVE pool source (loop mount point, or raw source)")
    init_parser.add_argument("--pool-size", default="", help="EFFECTIVE pool size (empty for a role-built loop)")
    init_parser.add_argument("--dry-run", action="store_true", help="print the preseed without applying it")

    delete_pool_parser: argparse.ArgumentParser = sub.add_parser(
        "delete-pool", help="detach default profile root + delete the pool + unmount the loop + drop its fstab line")
    delete_pool_parser.add_argument("--mountpoint", required=True, help="the loop mount point to unmount / clear from fstab")
    delete_pool_parser.add_argument("--dry-run", action="store_true", help="print actions without running them")
    return parser


def main() -> int:
    args: argparse.Namespace = build_arg_parser().parse_args()
    if args.subcommand == "status":
        return cmd_status(args.root, args.json)
    if args.subcommand == "verify":
        return cmd_verify(args.root, args.expect_driver, args.expect_source,
                          args.expect_loop_backing, args.json)
    if args.subcommand == "build-loop":
        return cmd_build_loop(args.source, args.size, args.mountpoint, dry_run=args.dry_run)
    if args.subcommand == "init":
        return cmd_init(args.driver, args.pool_source, args.pool_size, dry_run=args.dry_run)
    return cmd_delete_pool(args.mountpoint, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as command_failure:
        # A mutating step (mkfs / mount / incus ...) failed. incus's own reason is
        # already on stderr; print a clean one-liner instead of a Python traceback,
        # and propagate the non-zero exit so the calling ansible task fails loudly.
        failed_command: str = (shlex.join(command_failure.cmd)
                               if isinstance(command_failure.cmd, list) else str(command_failure.cmd))
        print(f"incus_storage_pool.py: command failed (exit {command_failure.returncode}): {failed_command}",
              file=sys.stderr)
        sys.exit(command_failure.returncode or 1)
