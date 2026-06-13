#!/usr/bin/env python3
"""Unit tests for `qvm`'s pure decision/parsing helpers.

Scope (same philosophy as roles/vm_incus/files/test_incus_storage_pool.py):
only the pure, fixture-only logic - conf render/parse, the `.ports` and
`.sha256` parsers, cloud-init user-data rendering, and the cwd->VM binding
resolution. No quickemu, no qemu, no network, no sockets; what needs the real
stack (quickemu boot, QGA against a live agent, virt-builder) is host-only.

Run:  cd roles/vm_quickemu/files && python3 -m unittest test_qvm -v
"""

import importlib.util
import os
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

# `qvm` is an extensionless executable, so name the loader explicitly (the
# default spec resolution only recognizes .py).
_THIS_DIR: str = os.path.dirname(os.path.abspath(__file__))
_QVM_LOADER = SourceFileLoader("qvm", os.path.join(_THIS_DIR, "qvm"))
_QVM_SPEC = importlib.util.spec_from_loader("qvm", _QVM_LOADER)
assert _QVM_SPEC is not None
qvm = importlib.util.module_from_spec(_QVM_SPEC)
_QVM_LOADER.exec_module(qvm)


class TestConfRenderAndParse(unittest.TestCase):
    """The conf qvm writes must round-trip through its own reader, and omit
    what was not asked for (no `iso=` ever - prebuilt disks boot directly)."""

    def test_render_parse_roundtrip_with_seed_iso(self) -> None:
        conf_text: str = qvm.render_conf_text(
            "linux", Path("/data/vms/tw/disk.qcow2"),
            fixed_iso_path=Path("/data/vms/tw/seed.iso"),
            disk_size="32G", ram="8G", cpu_cores="4")
        parsed_conf: dict[str, str] = qvm.parse_conf_text(conf_text)
        self.assertEqual(parsed_conf["guest_os"], "linux")
        self.assertEqual(parsed_conf["disk_img"], "/data/vms/tw/disk.qcow2")
        self.assertEqual(parsed_conf["fixed_iso"], "/data/vms/tw/seed.iso")
        self.assertEqual(parsed_conf["disk_size"], "32G")
        self.assertEqual(parsed_conf["ram"], "8G")
        self.assertEqual(parsed_conf["cpu_cores"], "4")
        self.assertNotIn("iso", parsed_conf)  # prebuilt disk: no installer media line

    def test_render_omits_unset_optionals(self) -> None:
        conf_text: str = qvm.render_conf_text(
            "linux", Path("/v/d.qcow2"), fixed_iso_path=None,
            disk_size="32G", ram="", cpu_cores="")
        parsed_conf: dict[str, str] = qvm.parse_conf_text(conf_text)
        self.assertNotIn("fixed_iso", parsed_conf)
        self.assertNotIn("ram", parsed_conf)
        self.assertNotIn("cpu_cores", parsed_conf)

    def test_parse_skips_comments_and_junk(self) -> None:
        parsed_conf: dict[str, str] = qvm.parse_conf_text(
            "#!/usr/bin/env quickemu --vm\n"
            "# a comment\n"
            'guest_os="windows"\n'
            "not an assignment line\n"
            "disk_img=unquoted/path.qcow2\n")
        self.assertEqual(parsed_conf["guest_os"], "windows")
        self.assertEqual(parsed_conf["disk_img"], "unquoted/path.qcow2")
        self.assertEqual(len(parsed_conf), 2)


class TestPortsParser(unittest.TestCase):
    """quickemu records `ssh,<port>` in `<vm>.ports` at boot - the only line
    `shell` depends on."""

    def test_finds_ssh_port(self) -> None:
        ports_text: str = "spice,5930\nssh,22220\nmonitor-telnet,4440,localhost\n"
        self.assertEqual(qvm.parse_ssh_port(ports_text), 22220)

    def test_no_ssh_line_returns_none(self) -> None:
        self.assertIsNone(qvm.parse_ssh_port("spice,5930\n"))
        self.assertIsNone(qvm.parse_ssh_port(""))
        self.assertIsNone(qvm.parse_ssh_port("ssh,not-a-port\n"))


class TestSha256Parser(unittest.TestCase):
    """The publisher `.sha256` file: `<hex>  <filename>` lines (a leading `*`
    marks binary mode in coreutils format)."""

    SHA256_TEXT: str = (
        "abc123  openSUSE-Tumbleweed-Minimal-VM.x86_64-Cloud.qcow2\n"
        "def456 *other-file.iso\n")

    def test_matches_exact_filename(self) -> None:
        self.assertEqual(
            qvm.parse_sha256_line(self.SHA256_TEXT,
                                  "openSUSE-Tumbleweed-Minimal-VM.x86_64-Cloud.qcow2"),
            "abc123")

    def test_matches_binary_marker_filename(self) -> None:
        self.assertEqual(qvm.parse_sha256_line(self.SHA256_TEXT, "other-file.iso"), "def456")

    def test_missing_filename_returns_none(self) -> None:
        self.assertIsNone(qvm.parse_sha256_line(self.SHA256_TEXT, "nope.qcow2"))


class TestCwdBindingResolution(unittest.TestCase):
    """`choose_vm_for_cwd`: exact dir first, then NEAREST ancestor; same-depth
    ambiguity raises (the caller dies with a `--name` hint)."""

    @staticmethod
    def _record(vm_name: str, init_at_dir: str) -> "qvm.VmRecord":
        return qvm.VmRecord(vm_name, Path(f"/vms/{vm_name}.conf"), Path(f"/vms/{vm_name}"),
                            {"init_at_dir": init_at_dir})

    def test_exact_dir_wins(self) -> None:
        vm_records = [self._record("a", "/home/u/proj"), self._record("b", "/home/u")]
        chosen = qvm.choose_vm_for_cwd(vm_records, Path("/home/u/proj"))
        assert chosen is not None
        self.assertEqual(chosen.vm_name, "a")

    def test_nearest_ancestor_wins(self) -> None:
        vm_records = [self._record("root-vm", "/home/u"), self._record("proj-vm", "/home/u/proj")]
        chosen = qvm.choose_vm_for_cwd(vm_records, Path("/home/u/proj/sub/dir"))
        assert chosen is not None
        self.assertEqual(chosen.vm_name, "proj-vm")

    def test_no_binding_returns_none(self) -> None:
        vm_records = [self._record("a", "/elsewhere")]
        self.assertIsNone(qvm.choose_vm_for_cwd(vm_records, Path("/home/u/proj")))

    def test_unbound_meta_is_ignored(self) -> None:
        unbound_record = qvm.VmRecord("x", Path("/vms/x.conf"), Path("/vms/x"), {})
        self.assertIsNone(qvm.choose_vm_for_cwd([unbound_record], Path("/home/u")))

    def test_two_bindings_same_dir_raise(self) -> None:
        vm_records = [self._record("a", "/home/u/proj"), self._record("b", "/home/u/proj")]
        with self.assertRaises(ValueError):
            qvm.choose_vm_for_cwd(vm_records, Path("/home/u/proj"))


class TestCloudInitUserData(unittest.TestCase):
    """The Tumbleweed seed must create the key-only user AND install the guest
    agent on first boot (that is what makes `qvm exec` work with zero
    interactive setup)."""

    def test_user_key_and_agent_present(self) -> None:
        user_data_text: str = qvm.render_cloud_init_user_data(
            "twvm", "ssh-ed25519 AAAA... qvm-twvm")
        self.assertTrue(user_data_text.startswith("#cloud-config\n"))
        self.assertIn(f"name: {qvm.TUMBLEWEED_SSH_USER}", user_data_text)
        self.assertIn("ssh-ed25519 AAAA... qvm-twvm", user_data_text)
        self.assertIn("qemu-guest-agent", user_data_text)
        self.assertIn("lock_passwd: true", user_data_text)


class TestVmNameValidation(unittest.TestCase):
    def test_names(self) -> None:
        self.assertTrue(qvm.VM_NAME_RE.match("debian"))
        self.assertTrue(qvm.VM_NAME_RE.match("tw-builder_2"))
        self.assertFalse(qvm.VM_NAME_RE.match("-bad"))
        self.assertFalse(qvm.VM_NAME_RE.match("has space"))
        self.assertFalse(qvm.VM_NAME_RE.match("a" * 64))


if __name__ == "__main__":
    unittest.main()
