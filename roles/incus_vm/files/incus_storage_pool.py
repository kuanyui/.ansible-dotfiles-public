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

`resolve` (READ-ONLY) is the same idea for the storage-layout DECISION: it folds
the `_incus_pool_build_loop` / `_incus_effective_pool_*` `set_fact` chain out of
ansible and answers "what layout does this install run use?" - crucially, once a
`default` pool exists it FOLLOWS the recorded `storage-info.json` instead of the
passed/default vars, so a re-run can't repoint the pool's record at the wrong `.img`.

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
INCUS_VAR_DIR: str = "/var/lib/incus"  # incus daemon state root; the `default` pool lives at storage-pools/default


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


def mounts_of_backing_file(backing_file: str) -> list[dict[str, str]]:
    """Every `/proc/mounts` entry that is the loop `.img` `backing_file`: the loop
    mount, incus's bind mount onto the pool path, and one entry per live btrfs
    subvolume (a running instance). Each line's device (field 0) is resolved through
    the loop driver before comparing, so it matches whether `/proc/mounts` shows the
    raw `/dev/loopN` OR (as `mount`/libmount renders it) the backing file itself -
    that single file appearing many times is exactly the "repeated mounts". Returns
    `{mount_target, fstype, btrfs_subvol}` per match (`btrfs_subvol` from the `subvol=`
    option, '' if absent). Empty when `backing_file` is unset / `/proc/mounts` unreadable."""
    matching_mounts: list[dict[str, str]] = []
    if not backing_file:
        return matching_mounts
    try:
        proc_mounts_text: str = open(PROC_MOUNTS_PATH).read()
    except OSError:
        return matching_mounts
    for mount_line in proc_mounts_text.splitlines():
        fields: list[str] = mount_line.split()
        if len(fields) < 4 or loop_backing_file_of(fields[0]) != backing_file:
            continue
        mount_options: list[str] = fields[3].split(",")
        btrfs_subvol: str = next(
            (option.split("=", 1)[1] for option in mount_options if option.startswith("subvol=")), "")
        matching_mounts.append({
            # /proc/mounts escapes spaces in the mount target as the octal \040.
            "mount_target": fields[1].replace("\\040", " "),
            "fstype": fields[2],
            "btrfs_subvol": btrfs_subvol,
        })
    return matching_mounts


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
    # The mount picture is computed ONCE here; its resolved loop `.img` (`backing_file`,
    # e.g. /data/vm/incus-btrfs.img) is then the key for `mounts_of_backing_file` - every
    # OTHER mount of that same file (the incus bind + each running instance's subvolume),
    # which the relationship section decodes. Only meaningful for the role's loop layout.
    mount_at_probe: dict[str, Any] = mount_state_of(mountpoint_to_probe)
    is_loop_mount: bool = mount_at_probe["mounted"] and mount_at_probe["device"].startswith("/dev/loop")
    loop_device_mounts: list[dict[str, str]] = (
        mounts_of_backing_file(mount_at_probe["backing_file"]) if is_loop_mount else [])
    return {
        "recorded": recorded,
        "live_pool": live,
        "mount": mount_at_probe,
        "mountpoint": mountpoint_to_probe,
        "fstab_line": fstab_line_for(mountpoint_to_probe),
        "loop_file": recorded_loop_file,
        "loop_footprint": loop_file_footprint(recorded_loop_file) if recorded_loop_file else {"exists": False, "on_disk_bytes": 0, "logical_bytes": 0},
        "loop_device_mounts": loop_device_mounts,
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


def describe_loop_device_mount(mount_target: str, btrfs_subvol: str,
                               loop_mountpoint: str, default_pool_path: str) -> str:
    """Label one mount of the loop `.img` by its ROLE so a raw `mount` line reads in
    plain terms: the fstab loop mount, incus's bind mount onto the pool path, or a
    running instance's btrfs subvolume. The instance case is named by its `subvol=`
    (e.g. `virtual-machines/<vm>`), because incus mounts it at an INTERNAL target like
    `devices/<vm>/config.mount`, not under the pool path. '' when it is none of these."""
    if mount_target == loop_mountpoint:
        return "the loop mount; your /etc/fstab line"
    if mount_target == default_pool_path:
        return "incus bind mount; the pool root"
    if mount_target.startswith(default_pool_path + "/"):
        return f"subvolume: {mount_target[len(default_pool_path) + 1:]}"
    running_instance_subvol: str = (btrfs_subvol or "").lstrip("/")
    if running_instance_subvol:
        return f"running instance: {running_instance_subvol}"
    return ""


def render_mount_relationship(data: dict[str, Any]) -> list[str]:
    """Plain-language explanation, for the END of `status`, of how the default
    btrfs-loop layout is actually mounted - written to answer the three things this
    layout makes people doubt: (1) is my `.img` even being used? (yes - it is the
    device on every line); (2) why does `storage-pools/default/virtual-machines/<vm>/`
    have a big `root.img` and is it eating my `/`? (no - that path is a BIND mount, so
    its blocks live in the `.img`, not on `/`); (3) why is the same file mounted over
    and over in `mount`? (the loop mount + incus's bind + one per running instance).
    The displayed device is the `.img` path itself (what `mount`/libmount shows), so it
    lines up with what the user sees. Returns [] for any non-loop layout (e.g. `dir`)."""
    mount: dict[str, Any] = data["mount"]
    loop_file: str = data["loop_file"]
    if not (loop_file and mount["mounted"] and mount["device"].startswith("/dev/loop")):
        return []
    loop_device: str = mount["device"]
    img_file: str = mount["backing_file"] or loop_file
    loop_mountpoint: str = data["mountpoint"]
    default_pool_path: str = f"{INCUS_VAR_DIR}/storage-pools/default"
    loop_device_mounts: list[dict[str, str]] = data.get("loop_device_mounts") or []
    lines: list[str] = ["-- how it is mounted (one `.img`, shared by every VM) --"]
    lines.append(f"  YES, all VM data is inside `{img_file}` - nothing lands outside it. Each VM is a")
    lines.append("  btrfs SUBVOLUME in that file; its disk `root.img` is just a file in the subvolume.")
    lines.append("  The chain, the one real file down to what incus shows:")
    lines.append("")
    lines.append(f"    {'.img file':<13}{img_file}")
    lines.append(f"    {'loop device':<13}{loop_device}   (the kernel exposes the .img as a block device)")
    lines.append(f"    {'btrfs mount':<13}{loop_mountpoint}   (your /etc/fstab loop line)")
    lines.append(f"    {'incus bind':<13}{default_pool_path}   (incus's canonical pool path)")
    lines.append(f"    {'per-VM disk':<13}{default_pool_path}/virtual-machines/<vm>/root.img   (a subvolume; the VM's disk)")
    lines.append("")
    lines.append(f"  `{default_pool_path}/` is that BIND mount, so whatever you")
    lines.append("  `ls` there (e.g. a large `root.img`) really lives inside the `.img` above, NOT on `/`.")
    if loop_device_mounts:
        lines.append("")
        lines.append(f"  Right now `{img_file}` is mounted {len(loop_device_mounts)}x -"
                     " in `mount` each line below is this SAME file:")
        for loop_device_mount in loop_device_mounts:
            mount_role: str = describe_loop_device_mount(
                loop_device_mount["mount_target"], loop_device_mount["btrfs_subvol"],
                loop_mountpoint, default_pool_path)
            role_note: str = f"   ({mount_role})" if mount_role else ""
            lines.append(f"    {img_file}  {loop_device_mount['mount_target']}{role_note}")
    return lines


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
    relationship_section: list[str] = render_mount_relationship(data)
    if relationship_section:
        lines.append("")
        lines.extend(relationship_section)
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


# ---------- resolve: decide the EFFECTIVE storage layout for an install run ----------
# The ONE place that answers "what storage does this `make incus-install` use?" - kept here, in
# readable + testable Python, instead of the `set_fact`/`when:` Jinja chains it replaces in
# tasks/incus_host_install.yml. The rule: once a `default` pool EXISTS with a recorded layout, we
# FOLLOW that record (what the pool was built with) and ignore the passed/default vars - so a re-run
# (commonly just to redeploy `ivm`) that omits or changes INCUS_STORAGE_POOL_* never re-derives
# storage from the role defaults and never pollutes storage-info.json. ansible calls this once and
# consumes the JSON (effective preseed source/size, the role-built-loop facts, the exact record dict).


def resolve_layout(root: str, already_initialized: bool, driver: str, source: str,
                   size: str, mountpoint: str) -> tuple[dict[str, Any], bool, bool]:
    """Pure decision: from the REQUESTED layout + whether a `default` pool already exists, return
    `(resolved, following, loop_img_missing)`. FOLLOWING (pool exists AND a usable record is on
    disk) -> the layout the pool was BUILT with, taken verbatim from the record; otherwise (first
    install / no record yet) -> derived from the request. `resolved` carries everything the install
    needs downstream: the effective preseed `pool_source`/`pool_size`, the role-built-loop facts
    (`build_loop`/`loop_file`/`mountpoint`), and the exact `storage-info.json` `record` dict. Only
    reads the record + `stat`s the loop file; never mutates."""
    record: dict[str, Any] | None = read_storage_info(root)
    following: bool = bool(already_initialized and record and str(record.get("driver") or ""))
    loop_img_missing: bool = False
    if following and record is not None:
        effective_driver: str = str(record.get("driver") or "")
        build_loop: bool = bool(record.get("build_loop"))
        loop_file: str = str(record.get("loop_file") or "")
        loop_mountpoint: str = str(record.get("mountpoint") or "")
        effective_source: str = str(record.get("source") or "")
        declared_size: str = str(record.get("size") or "")
        # The pool exists but its loop `.img` is gone (most often: the disk holding it is not
        # mounted) - the caller turns this into a loud STOP rather than rebuild empty storage.
        loop_img_missing = bool(build_loop and loop_file and not os.path.exists(loop_file))
    else:
        effective_driver = driver
        # Role-built loop = btrfs + `source` is a FILE path (absent, or an existing regular file)
        # + a size. A dir / existing subvolume / block-device source is handed to incus as-is.
        source_is_loop_file: bool = bool(source) and (not os.path.exists(source) or os.path.isfile(source))
        build_loop = (driver == "btrfs") and bool(source) and bool(size) and source_is_loop_file
        loop_file = source if build_loop else ""
        loop_mountpoint = mountpoint if build_loop else ""
        effective_source = mountpoint if build_loop else source
        declared_size = size
    # A role-built loop hands incus the already-mounted btrfs FS (so NO size in the preseed); every
    # other form passes the size through. The record keeps the DECLARED size either way.
    preseed_size: str = "" if build_loop else declared_size
    resolved: dict[str, Any] = {
        "following": following,
        "already_initialized": already_initialized,
        "driver": effective_driver,
        "build_loop": build_loop,
        "loop_file": loop_file,
        "mountpoint": loop_mountpoint,
        "pool_source": effective_source,
        "pool_size": preseed_size,
        "declared_size": declared_size,
        "record": {
            "driver": effective_driver,
            "build_loop": build_loop,
            "loop_file": loop_file,
            "mountpoint": loop_mountpoint,
            "source": effective_source,
            "size": declared_size,
        },
    }
    return resolved, following, loop_img_missing


def _loop_missing_banner(record: dict[str, Any]) -> str:
    """The loud STOP message (-> stderr) when a `default` pool exists but its recorded loop `.img`
    is gone: lead with the cheap, non-destructive fix (remount its disk) before the teardown path."""
    loop_file: str = str(record.get("loop_file") or "")
    loop_mountpoint: str = str(record.get("mountpoint") or "")
    bar: str = "=" * 60
    return "\n".join([
        "", bar,
        " incus `default` pool exists, but its recorded loop file is",
        " MISSING - stopping (never auto-rebuilding empty storage).",
        bar,
        f" recorded `.img`: {loop_file}",
        f" mounted at:      {loop_mountpoint or '(n/a)'}",
        "",
        " The file is not on disk. The likeliest cause is its disk simply",
        " is not mounted - check that FIRST; a remount fixes it WITHOUT",
        " touching any VM data:",
        "",
        f"     mount {loop_mountpoint or '<mountpoint>'}    # or: mount -a",
        "",
        " Only if the `.img` is TRULY gone (its data already lost) rebuild",
        " from scratch (DESTROYS the pool + every VM, then recreates it):",
        "",
        f"     make incus-teardown-host && make incus-install"
        f" INCUS_STORAGE_POOL_SOURCE={loop_file} INCUS_STORAGE_POOL_SIZE={record.get('size') or ''}",
        bar, "",
    ])


def _override_ignored_warning(record: dict[str, Any]) -> str:
    """The WARNING (kept, not failed) shown when INCUS_STORAGE_POOL_* was passed on an already-
    initialized host: the record is authoritative; teardown is the only way to actually change."""
    bar: str = "=" * 60
    record_source: str = str(record.get("loop_file") or record.get("source") or "")
    return "\n".join([
        bar,
        " WARNING - incus `default` pool already exists, so your",
        " INCUS_STORAGE_POOL_* override is IGNORED (a pool is never",
        " re-pointed). The ESTABLISHED record is kept:",
        bar,
        f"   record driver = {record.get('driver') or '?'}",
        f"   record source = {record_source or '?'}",
        f"   record size   = {record.get('size') or '?'}",
        "",
        " If that already matches what you intended, just drop the",
        " INCUS_STORAGE_POOL_* args. To genuinely change storage:",
        "     make incus-teardown-host && make incus-install INCUS_STORAGE_POOL_*=...",
        bar,
    ])


def cmd_resolve(root: str, already_initialized: bool, driver: str, source: str, size: str,
                mountpoint: str, overrides_passed: bool) -> int:
    """Print (JSON, stdout) the effective storage layout for this install run; ansible consumes it.
    Two guards on the FOLLOWING path: (Q2) the recorded loop `.img` has vanished -> loud STOP
    (banner to stderr, non-zero exit, so the `script` task fails); (Q1) overrides were passed but a
    pool already exists -> a WARNING carried in `resolved["warnings"]` (kept, not failed - ansible
    surfaces it)."""
    resolved, following, loop_img_missing = resolve_layout(
        root, already_initialized, driver, source, size, mountpoint)
    if loop_img_missing:
        sys.stderr.write(_loop_missing_banner(resolved["record"]))
        return 2
    resolved["warnings"] = [_override_ignored_warning(resolved["record"])] if (following and overrides_passed) else []
    print(json.dumps(resolved, indent=2))
    return 0


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
    """`truncate` a sparse `.img` at `source` if absent, then `mkfs.btrfs` it. Returns
    True if it changed. A freshly-truncated file is formatted unconditionally; a
    PRE-EXISTING file is formatted ONLY when `blkid` positively confirms it holds no
    filesystem (exit 2 = "nothing found"). Any OTHER `blkid` outcome - a reported
    filesystem (exit 0 with a TYPE), an ambivalent multi-signature (exit 8), a usage
    error (exit 4), or `blkid` missing (exit 127) - means we CANNOT prove the file is
    empty, so we REFUSE to mkfs rather than risk erasing existing VM data. (The earlier
    version keyed only on blkid's stdout being empty, which is ALSO what a missing /
    erroring blkid returns - that would reformat a file that may hold the pool.)
    `size` is the incus form e.g. `100GiB`; `truncate`'s binary `G`/`T` already mean
    GiB/TiB, so we just drop the `iB` (matches the old role's regex)."""
    if not os.path.exists(source):
        run_privileged(["truncate", f"--size={re.sub(r'iB$', '', size)}", source], dry_run=dry_run)
        # A just-created sparse file is definitionally empty -> format it without probing
        # (blkid on a not-yet-created file would be meaningless under --dry-run anyway).
        run_privileged(["mkfs.btrfs", source], dry_run=dry_run)
        return True
    # Pre-existing file: decide from blkid's EXIT CODE, never from an empty stdout alone -
    # blkid prints nothing both when the file has no filesystem (exit 2) AND when it is
    # missing / errors (exit 4/8/127), so the old empty-string test would mkfs (ERASE) a
    # file that may be holding the pool.
    blkid_rc, blkid_type_output, blkid_stderr = run_capture(
        ["blkid", "--output", "value", "--match-tag", "TYPE", source])
    existing_fs_type: str = blkid_type_output.strip()
    if blkid_rc == 0 and existing_fs_type:
        return False  # already carries a filesystem -> NEVER reformat
    if blkid_rc != 2:
        sys.stderr.write("\n".join([
            "", "=" * 60,
            " incus_storage_pool.py: REFUSING to mkfs.btrfs - cannot confirm",
            f" `{source}` is empty (blkid exit {blkid_rc}).",
            "=" * 60,
            " mkfs would ERASE whatever the file holds. blkid did NOT return",
            " its 'nothing found' code (2): it is missing (exit 127), hit a",
            " usage error (4), or found an ambivalent multi-signature (8).",
            " Refusing rather than risk destroying VM data.",
            f" blkid stderr: {blkid_stderr.strip() or '(none)'}",
            "=" * 60, "",
        ]))
        raise SystemExit(1)
    run_privileged(["mkfs.btrfs", source], dry_run=dry_run)  # blkid exit 2 -> confirmed empty
    return True


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
    resolve_parser: argparse.ArgumentParser = sub.add_parser(
        "resolve", help="decide + print (JSON) the effective storage layout for an install run "
                        "(follows the recorded layout once a `default` pool exists)")
    resolve_parser.add_argument("--already-initialized", required=True, choices=["true", "false"],
                                help="whether a `default` pool already exists (ansible's probe)")
    resolve_parser.add_argument("--driver", default="", help="REQUESTED pool driver")
    resolve_parser.add_argument("--source", default="",
                                help="REQUESTED source (a `.img` path -> role-built loop; else dir / subvolume / device)")
    resolve_parser.add_argument("--size", default="", help="REQUESTED size (e.g. 100GiB)")
    resolve_parser.add_argument("--mountpoint", default="", help="loop mount point for a role-built loop")
    resolve_parser.add_argument("--overrides-passed", action="store_true",
                                help="the user passed INCUS_STORAGE_POOL_* explicitly (drives the ignored-override warning)")

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
    if args.subcommand == "resolve":
        return cmd_resolve(args.root, args.already_initialized == "true", args.driver,
                           args.source, args.size, args.mountpoint, args.overrides_passed)
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
