#!/usr/bin/env python3
"""Unit tests for the DATA-SAFETY decision logic in `incus_storage_pool.py`.

Scope (deliberately narrow): the pure / fixture-only guards that decide whether a
`make incus-install` run could erase or shadow storage - the bugs that "lose data".
They run with NO root, NO loop devices, NO incus, in milliseconds, so the
combinatorial guard matrix (pool-exists x record-present x build_loop x img-missing
x override) is exercised exhaustively HERE instead of by hand-staging a VM per case.

What is intentionally NOT covered (it needs the real kernel / incus, so it belongs in
`make incus-sandbox` + a real VM, never in mocks): the ACTUAL effect of `truncate` /
`mkfs.btrfs` / loop `mount` eviction / `incus admin init`, and the real output shape
of `incus storage list --format csv`. Mocking those would test the mock, not reality.

Run:  python3 -m unittest discover -s roles/incus_vm/files
  or: cd roles/incus_vm/files && python3 -m unittest test_incus_storage_pool -v
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

# Load the module under test by FILE PATH, so the suite runs from any CWD without
# depending on sys.path / package layout. Imported as "incus_storage_pool" (not
# "__main__"), so its `if __name__ == "__main__"` CLI block does not execute.
_THIS_DIR: str = os.path.dirname(os.path.abspath(__file__))
_MODULE_SPEC = importlib.util.spec_from_file_location(
    "incus_storage_pool", os.path.join(_THIS_DIR, "incus_storage_pool.py"))
assert _MODULE_SPEC is not None and _MODULE_SPEC.loader is not None
incus_storage_pool = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(incus_storage_pool)


def _privileged_program_calls(run_privileged_mock: MagicMock) -> list[str]:
    """The argv[0] (the program) of every `run_privileged` call recorded by the mock,
    e.g. `['truncate', 'mkfs.btrfs']` - what the function WOULD have executed."""
    return [recorded_call.args[0][0] for recorded_call in run_privileged_mock.call_args_list]


class TestEnsureLoopFileMkfsGuard(unittest.TestCase):
    """`ensure_loop_file` must NEVER `mkfs.btrfs` a file it cannot PROVE is empty - that
    one check is all that stands between a re-run and an erased pool `.img`. The decision
    keys on blkid's EXIT CODE (2 = confirmed empty), not on an empty stdout (which also
    comes back when blkid is missing or errors)."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_dir: str = self._tmp_dir.name

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _call_ensure_loop_file(self, *, file_exists: bool, blkid_result: tuple[int, str, str]
                               ) -> tuple[bool | None, MagicMock, SystemExit | None]:
        """Run `ensure_loop_file` with `run_privileged` (recorder) + `run_capture` (canned
        blkid) mocked. Returns `(return_value_or_None, run_privileged_mock, SystemExit_or_None)`."""
        loop_img_path: str = os.path.join(self.tmp_dir, "incus-storage.img")
        if file_exists:
            open(loop_img_path, "wb").close()
        returned: bool | None = None
        raised_system_exit: SystemExit | None = None
        with patch.object(incus_storage_pool, "run_privileged") as run_privileged_mock, \
                patch.object(incus_storage_pool, "run_capture", return_value=blkid_result), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                returned = incus_storage_pool.ensure_loop_file(loop_img_path, "100GiB", dry_run=False)
            except SystemExit as system_exit:
                raised_system_exit = system_exit
        return returned, run_privileged_mock, raised_system_exit

    def test_absent_file_is_truncated_then_formatted(self) -> None:
        returned, run_privileged_mock, raised_system_exit = self._call_ensure_loop_file(
            file_exists=False, blkid_result=(2, "", ""))
        self.assertIsNone(raised_system_exit)
        self.assertTrue(returned)
        self.assertEqual(_privileged_program_calls(run_privileged_mock), ["truncate", "mkfs.btrfs"])

    def test_existing_btrfs_file_is_never_reformatted(self) -> None:
        # blkid exit 0 WITH a TYPE -> the file already holds a filesystem.
        returned, run_privileged_mock, raised_system_exit = self._call_ensure_loop_file(
            file_exists=True, blkid_result=(0, "btrfs\n", ""))
        self.assertIsNone(raised_system_exit)
        self.assertFalse(returned)
        self.assertNotIn("mkfs.btrfs", _privileged_program_calls(run_privileged_mock))

    def test_existing_empty_file_is_formatted_only_on_blkid_exit_2(self) -> None:
        returned, run_privileged_mock, raised_system_exit = self._call_ensure_loop_file(
            file_exists=True, blkid_result=(2, "", ""))
        self.assertIsNone(raised_system_exit)
        self.assertTrue(returned)
        self.assertEqual(_privileged_program_calls(run_privileged_mock), ["mkfs.btrfs"])

    def test_blkid_missing_refuses_to_format(self) -> None:
        # exit 127 (blkid not found) -> empty stdout, but that is NOT proof of an empty file.
        _returned, run_privileged_mock, raised_system_exit = self._call_ensure_loop_file(
            file_exists=True, blkid_result=(127, "", "blkid: not found"))
        self.assertIsInstance(raised_system_exit, SystemExit)
        self.assertNotIn("mkfs.btrfs", _privileged_program_calls(run_privileged_mock))

    def test_blkid_usage_error_refuses_to_format(self) -> None:
        _returned, run_privileged_mock, raised_system_exit = self._call_ensure_loop_file(
            file_exists=True, blkid_result=(4, "", "usage error"))
        self.assertIsInstance(raised_system_exit, SystemExit)
        self.assertNotIn("mkfs.btrfs", _privileged_program_calls(run_privileged_mock))

    def test_blkid_ambivalent_multisignature_refuses_to_format(self) -> None:
        # exit 8 = more than one signature found -> there IS data; refusing protects it.
        _returned, run_privileged_mock, raised_system_exit = self._call_ensure_loop_file(
            file_exists=True, blkid_result=(8, "", ""))
        self.assertIsInstance(raised_system_exit, SystemExit)
        self.assertNotIn("mkfs.btrfs", _privileged_program_calls(run_privileged_mock))


class TestResolveLayout(unittest.TestCase):
    """`resolve_layout` decides what storage a run uses. Data-safety contract: once a
    `default` pool exists WITH a record, FOLLOW the record (never re-point to a different
    or empty `.img`); flag a vanished recorded `.img` as `loop_img_missing` (the caller
    turns that into a loud STOP, not a silent empty rebuild)."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.root: str = self._tmp_dir.name

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _write_record(self, recorded_layout: dict[str, Any]) -> None:
        with open(os.path.join(self.root, "storage-info.json"), "w") as record_file:
            json.dump(recorded_layout, record_file)

    def test_following_record_ignores_passed_vars(self) -> None:
        # Pool exists + a record on disk -> follow the RECORD even when the caller passes a
        # totally different driver/source (a re-run that omitted/changed INCUS_STORAGE_POOL_*
        # must not re-point the pool).
        recorded_loop_img: str = os.path.join(self.root, "recorded.img")
        open(recorded_loop_img, "wb").close()
        self._write_record({"driver": "btrfs", "build_loop": True, "loop_file": recorded_loop_img,
                            "mountpoint": "/var/lib/incus-storage", "source": "/var/lib/incus-storage",
                             "size": "500GiB"})
        resolved, following, loop_img_missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="dir", source="/somewhere/else", size="", mountpoint="/other/mnt")
        self.assertTrue(following)
        self.assertFalse(loop_img_missing)
        self.assertEqual(resolved["driver"], "btrfs")              # from the record, NOT "dir"
        self.assertEqual(resolved["loop_file"], recorded_loop_img)  # NOT "/somewhere/else"
        self.assertEqual(resolved["pool_source"], "/var/lib/incus-storage")

    def test_following_record_with_missing_img_flags_loop_img_missing(self) -> None:
        missing_loop_img: str = os.path.join(self.root, "gone.img")  # never created
        self._write_record({"driver": "btrfs", "build_loop": True, "loop_file": missing_loop_img,
                            "mountpoint": "/var/lib/incus-storage", "source": "/var/lib/incus-storage",
                             "size": "500GiB"})
        _resolved, following, loop_img_missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="btrfs", source=missing_loop_img, size="500GiB", mountpoint="/var/lib/incus-storage")
        self.assertTrue(following)
        self.assertTrue(loop_img_missing)

    def test_following_record_with_present_img_is_not_missing(self) -> None:
        present_loop_img: str = os.path.join(self.root, "present.img")
        open(present_loop_img, "wb").close()
        self._write_record({"driver": "btrfs", "build_loop": True, "loop_file": present_loop_img,
                            "mountpoint": "/var/lib/incus-storage", "source": "/var/lib/incus-storage",
                             "size": "500GiB"})
        _resolved, _following, loop_img_missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="btrfs", source=present_loop_img, size="500GiB", mountpoint="/var/lib/incus-storage")
        self.assertFalse(loop_img_missing)

    def test_first_install_btrfs_file_source_derives_role_built_loop(self) -> None:
        # No record + not yet initialized -> derive from the request. btrfs + a file-path
        # source + a size -> the role builds + owns the loop; incus gets the MOUNT (no size).
        new_loop_img: str = os.path.join(self.root, "new.img")  # absent -> a to-be-built loop file
        resolved, following, loop_img_missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=False,
            driver="btrfs", source=new_loop_img, size="500GiB", mountpoint="/var/lib/incus-storage")
        self.assertFalse(following)
        self.assertFalse(loop_img_missing)
        self.assertTrue(resolved["build_loop"])
        self.assertEqual(resolved["loop_file"], new_loop_img)
        self.assertEqual(resolved["pool_source"], "/var/lib/incus-storage")
        self.assertEqual(resolved["pool_size"], "")          # role-built loop -> no size in preseed
        self.assertEqual(resolved["declared_size"], "500GiB")  # but the record keeps the declared size

    def test_first_install_dir_driver_builds_no_loop(self) -> None:
        resolved, _following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=False,
            driver="dir", source="", size="", mountpoint="/var/lib/incus-storage")
        self.assertFalse(resolved["build_loop"])
        self.assertEqual(resolved["driver"], "dir")

    def test_first_install_btrfs_existing_directory_source_builds_no_loop(self) -> None:
        # A btrfs source that is an existing DIRECTORY (a subvolume) is handed to incus
        # as-is, never mistaken for a loop file to mkfs.
        subvolume_dir: str = os.path.join(self.root, "subvol")
        os.mkdir(subvolume_dir)
        resolved, _following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=False,
            driver="btrfs", source=subvolume_dir, size="500GiB", mountpoint="/var/lib/incus-storage")
        self.assertFalse(resolved["build_loop"])

    def test_pool_exists_but_no_record_does_not_follow(self) -> None:
        # A hand-made pool (no storage-info.json): nothing to follow, so derive. resolve must
        # not claim `following`; ansible's driver-mismatch guard handles the rest.
        resolved, following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="btrfs", source=os.path.join(self.root, "x.img"), size="500GiB",
            mountpoint="/var/lib/incus-storage")
        self.assertFalse(following)
        self.assertEqual(resolved["driver"], "btrfs")

    def test_record_with_blank_driver_does_not_follow(self) -> None:
        self._write_record({"driver": "", "build_loop": False})
        _resolved, following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="btrfs", source="", size="", mountpoint="")
        self.assertFalse(following)

    # ---- `write_record`: may ansible persist the resolved record? ----
    # False exactly when a `default` pool exists WITHOUT a usable record: there the resolved
    # layout is just the passed/default vars, NOT the live pool, and persisting it would make
    # every later run FOLLOW that lie (e.g. a loud loop-img-missing STOP for an `.img` that
    # never existed - the "record pollution" bug).

    def test_first_install_write_record_is_true(self) -> None:
        resolved, _following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=False,
            driver="btrfs", source=os.path.join(self.root, "new.img"), size="500GiB",
            mountpoint="/var/lib/incus-storage")
        self.assertTrue(resolved["write_record"])

    def test_following_write_record_is_true(self) -> None:
        recorded_loop_img: str = os.path.join(self.root, "recorded.img")
        open(recorded_loop_img, "wb").close()
        self._write_record({"driver": "btrfs", "build_loop": True, "loop_file": recorded_loop_img,
                            "mountpoint": "/var/lib/incus-storage", "source": "/var/lib/incus-storage",
                             "size": "500GiB"})
        resolved, following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="btrfs", source="", size="", mountpoint="/var/lib/incus-storage")
        self.assertTrue(following)
        self.assertTrue(resolved["write_record"])  # echoing the record back is a no-op write

    def test_pool_exists_but_no_record_write_record_is_false(self) -> None:
        resolved, following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="btrfs", source=os.path.join(self.root, "x.img"), size="500GiB",
            mountpoint="/var/lib/incus-storage")
        self.assertFalse(following)
        self.assertFalse(resolved["write_record"])

    def test_pool_exists_with_unusable_record_write_record_is_false(self) -> None:
        self._write_record({"driver": "", "build_loop": False})  # blank driver -> not followable
        resolved, _following, _missing = incus_storage_pool.resolve_layout(
            self.root, already_initialized=True,
            driver="btrfs", source="", size="", mountpoint="")
        self.assertFalse(resolved["write_record"])


class TestEnsureMountedFromSource(unittest.TestCase):
    """The stale-loop eviction decision: mounting the new pool on top of a leftover loop
    from a PRIOR pool (possibly already `(deleted)`) would silently put it on the WRONG
    filesystem. A mismatched backing file must be `umount`ed BEFORE the `mount`."""

    def _recorded_argvs(self, mount_state: dict[str, Any]) -> list[list[str]]:
        with patch.object(incus_storage_pool, "mount_state_of", return_value=mount_state), \
                patch.object(incus_storage_pool, "run_privileged") as run_privileged_mock, \
                contextlib.redirect_stderr(io.StringIO()):
            incus_storage_pool.ensure_mounted_from_source(
                "/data/new.img", "/var/lib/incus-storage", dry_run=False)
        return [recorded_call.args[0] for recorded_call in run_privileged_mock.call_args_list]

    def test_already_mounted_from_same_source_is_noop(self) -> None:
        recorded_argvs = self._recorded_argvs({"mounted": True, "backing_file": "/data/new.img"})
        self.assertEqual(recorded_argvs, [])

    def test_stale_backing_is_evicted_before_mount(self) -> None:
        recorded_argvs = self._recorded_argvs({"mounted": True, "backing_file": "/data/OLD.img"})
        self.assertEqual(recorded_argvs, [["umount", "/var/lib/incus-storage"],
                                          ["mount", "/var/lib/incus-storage"]])

    def test_unmounted_just_mounts(self) -> None:
        recorded_argvs = self._recorded_argvs({"mounted": False, "backing_file": ""})
        self.assertEqual(recorded_argvs, [["mount", "/var/lib/incus-storage"]])


class TestFstabEditors(unittest.TestCase):
    """fstab editing must replace ONLY the line for our mountpoint and preserve every
    other entry + comment - a wrong rewrite could mount the pool over real data, or drop
    an unrelated filesystem."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.fstab_path: str = os.path.join(self._tmp_dir.name, "fstab")
        self._fstab_patcher = patch.object(incus_storage_pool, "FSTAB_PATH", self.fstab_path)
        self._fstab_patcher.start()

    def tearDown(self) -> None:
        self._fstab_patcher.stop()
        self._tmp_dir.cleanup()

    def _write_fstab(self, fstab_text: str) -> None:
        with open(self.fstab_path, "w") as fstab_file:
            fstab_file.write(fstab_text)

    def _read_fstab(self) -> str:
        with open(self.fstab_path) as fstab_file:
            return fstab_file.read()

    def test_ensure_replaces_only_matching_mountpoint_and_keeps_others(self) -> None:
        self._write_fstab(
            "# a comment\n"
            "UUID=root-fs / ext4 defaults 0 1\n"
            "/old/img /var/lib/incus-storage btrfs loop,nofail,noatime 0 0\n")
        with contextlib.redirect_stderr(io.StringIO()):
            fstab_changed: bool = incus_storage_pool.ensure_fstab_loop_line(
                "/data/new.img", "/var/lib/incus-storage", dry_run=False)
        self.assertTrue(fstab_changed)
        fstab_contents: str = self._read_fstab()
        self.assertIn("# a comment", fstab_contents)
        self.assertIn("UUID=root-fs / ext4 defaults 0 1", fstab_contents)       # untouched
        self.assertIn("/data/new.img /var/lib/incus-storage btrfs", fstab_contents)  # corrected in place
        self.assertNotIn("/old/img", fstab_contents)                            # stale source gone
        line_count_for_mountpoint: int = sum(
            1 for fstab_line in fstab_contents.splitlines()
            if len(fstab_line.split()) >= 2 and fstab_line.split()[1] == "/var/lib/incus-storage")
        self.assertEqual(line_count_for_mountpoint, 1)

    def test_ensure_is_idempotent(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            incus_storage_pool.ensure_fstab_loop_line(
                "/data/new.img", "/var/lib/incus-storage", dry_run=False)
            second_run_changed: bool = incus_storage_pool.ensure_fstab_loop_line(
                "/data/new.img", "/var/lib/incus-storage", dry_run=False)
        self.assertFalse(second_run_changed)

    def test_remove_drops_only_matching_mountpoint(self) -> None:
        self._write_fstab(
            "UUID=root-fs / ext4 defaults 0 1\n"
            "/data/new.img /var/lib/incus-storage btrfs loop,nofail,noatime 0 0\n")
        with contextlib.redirect_stderr(io.StringIO()):
            remove_changed: bool = incus_storage_pool.remove_fstab_line(
                "/var/lib/incus-storage", dry_run=False)
        self.assertTrue(remove_changed)
        fstab_contents: str = self._read_fstab()
        self.assertIn("UUID=root-fs", fstab_contents)
        self.assertNotIn("/var/lib/incus-storage", fstab_contents)

    def test_remove_is_noop_when_absent(self) -> None:
        self._write_fstab("UUID=root-fs / ext4 defaults 0 1\n")
        with contextlib.redirect_stderr(io.StringIO()):
            remove_changed: bool = incus_storage_pool.remove_fstab_line(
                "/var/lib/incus-storage", dry_run=False)
        self.assertFalse(remove_changed)


class TestVerdict(unittest.TestCase):
    """`verdict` is the post-install detection net: it must call out a silent wrong pool
    (driver mismatch) or a recorded loop that is not actually mounted from its `.img`
    (stale / ghost) - the exact 'lost data' symptoms."""

    @staticmethod
    def _gathered(*, live_pool: dict[str, Any], recorded: dict[str, Any] | None,
                  mount: dict[str, Any], mountpoint: str = "/var/lib/incus-storage") -> dict[str, Any]:
        return {"live_pool": live_pool, "recorded": recorded, "mount": mount, "mountpoint": mountpoint}

    def test_no_pool(self) -> None:
        state, _reasons = incus_storage_pool.verdict(self._gathered(
            live_pool={"present": False, "driver": "", "source": ""}, recorded=None,
            mount={"mounted": False, "backing_file": ""}))
        self.assertEqual(state, "no-pool")

    def test_driver_mismatch_is_flagged(self) -> None:
        state, reasons = incus_storage_pool.verdict(self._gathered(
            live_pool={"present": True, "driver": "dir", "source": ""},
            recorded={"driver": "btrfs"},
            mount={"mounted": False, "backing_file": ""}))
        self.assertEqual(state, "MISMATCH")
        self.assertTrue(any("driver" in reason for reason in reasons))

    def test_recorded_loop_not_mounted_is_flagged(self) -> None:
        state, reasons = incus_storage_pool.verdict(self._gathered(
            live_pool={"present": True, "driver": "btrfs", "source": "/var/lib/incus-storage"},
            recorded={"driver": "btrfs", "build_loop": True, "loop_file": "/data/x.img"},
            mount={"mounted": False, "backing_file": ""}))
        self.assertEqual(state, "MISMATCH")
        self.assertTrue(any("NOT mounted" in reason for reason in reasons))

    def test_recorded_loop_ghost_backing_is_flagged(self) -> None:
        state, reasons = incus_storage_pool.verdict(self._gathered(
            live_pool={"present": True, "driver": "btrfs", "source": "/var/lib/incus-storage"},
            recorded={"driver": "btrfs", "build_loop": True, "loop_file": "/data/x.img"},
            mount={"mounted": True, "backing_file": "/data/STALE.img"}))
        self.assertEqual(state, "MISMATCH")
        self.assertTrue(any(("stale" in reason or "ghost" in reason) for reason in reasons))

    def test_consistent(self) -> None:
        state, reasons = incus_storage_pool.verdict(self._gathered(
            live_pool={"present": True, "driver": "btrfs", "source": "/var/lib/incus-storage"},
            recorded={"driver": "btrfs", "build_loop": True, "loop_file": "/data/x.img"},
            mount={"mounted": True, "backing_file": "/data/x.img"}))
        self.assertEqual(state, "consistent")
        self.assertEqual(reasons, [])


class TestCmdResolveSafetyContract(unittest.TestCase):
    """`cmd_resolve` is what ansible's `script` task runs; these lock the exit-code
    contract the install path depends on: a vanished `.img` -> exit 2 (loud STOP), a
    normal resolve -> exit 0, an ignored override on an existing pool -> a kept warning."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.root: str = self._tmp_dir.name

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def _write_record(self, recorded_layout: dict[str, Any]) -> None:
        with open(os.path.join(self.root, "storage-info.json"), "w") as record_file:
            json.dump(recorded_layout, record_file)

    def test_missing_recorded_img_exits_2(self) -> None:
        self._write_record({"driver": "btrfs", "build_loop": True,
                            "loop_file": os.path.join(self.root, "gone.img"),
                            "mountpoint": "/var/lib/incus-storage", "source": "/var/lib/incus-storage",
                             "size": "500GiB"})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exit_code: int = incus_storage_pool.cmd_resolve(
                self.root, already_initialized=True, driver="btrfs",
                source="", size="", mountpoint="/var/lib/incus-storage", overrides_passed=False)
        self.assertEqual(exit_code, 2)

    def test_normal_resolve_exits_0_and_follows(self) -> None:
        present_loop_img: str = os.path.join(self.root, "present.img")
        open(present_loop_img, "wb").close()
        self._write_record({"driver": "btrfs", "build_loop": True, "loop_file": present_loop_img,
                            "mountpoint": "/var/lib/incus-storage", "source": "/var/lib/incus-storage",
                             "size": "500GiB"})
        with contextlib.redirect_stdout(io.StringIO()) as captured_stdout, \
                contextlib.redirect_stderr(io.StringIO()):
            exit_code: int = incus_storage_pool.cmd_resolve(
                self.root, already_initialized=True, driver="btrfs",
                source="", size="", mountpoint="/var/lib/incus-storage", overrides_passed=False)
        self.assertEqual(exit_code, 0)
        resolved_json: dict[str, Any] = json.loads(captured_stdout.getvalue())
        self.assertTrue(resolved_json["following"])
        self.assertEqual(resolved_json["warnings"], [])

    def test_pool_without_record_resolves_with_write_record_false(self) -> None:
        # The ansible-facing JSON contract for the "record pollution" fix: a `default` pool
        # with NO storage-info.json resolves fine (exit 0) but tells ansible NOT to persist
        # the derived record (it describes the vars, not the live pool).
        with contextlib.redirect_stdout(io.StringIO()) as captured_stdout, \
                contextlib.redirect_stderr(io.StringIO()):
            exit_code: int = incus_storage_pool.cmd_resolve(
                self.root, already_initialized=True, driver="btrfs",
                source=os.path.join(self.root, "x.img"), size="500GiB",
                mountpoint="/var/lib/incus-storage", overrides_passed=False)
        self.assertEqual(exit_code, 0)
        resolved_json: dict[str, Any] = json.loads(captured_stdout.getvalue())
        self.assertFalse(resolved_json["following"])
        self.assertFalse(resolved_json["write_record"])

    def test_ignored_override_keeps_a_warning(self) -> None:
        present_loop_img: str = os.path.join(self.root, "present.img")
        open(present_loop_img, "wb").close()
        self._write_record({"driver": "btrfs", "build_loop": True, "loop_file": present_loop_img,
                            "mountpoint": "/var/lib/incus-storage", "source": "/var/lib/incus-storage",
                             "size": "500GiB"})
        with contextlib.redirect_stdout(io.StringIO()) as captured_stdout, \
                contextlib.redirect_stderr(io.StringIO()):
            exit_code: int = incus_storage_pool.cmd_resolve(
                self.root, already_initialized=True, driver="dir",
                source="/elsewhere", size="", mountpoint="/other", overrides_passed=True)
        self.assertEqual(exit_code, 0)
        resolved_json: dict[str, Any] = json.loads(captured_stdout.getvalue())
        self.assertGreaterEqual(len(resolved_json["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
