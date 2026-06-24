#!/usr/bin/env python3
"""Unit tests for `pvm`'s pure helpers (parser + ported host-cli/distro logic).

No podman, no network: only the pure decision/parsing/argv functions. What needs
real podman (build / run / exec / commit) is exercised host-side in 3.2/3.3.

Run:  cd roles/vm_podman/files && python3 -m unittest test_pvm -v
"""

import importlib.util
import json
import os
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

# `pvm` is an extensionless executable, so name the loader explicitly (the default
# spec resolution only recognizes .py). Same trick as test_qvm.py.
_THIS_DIR: str = os.path.dirname(os.path.abspath(__file__))
_PVM_LOADER = SourceFileLoader("pvm", os.path.join(_THIS_DIR, "pvm"))
_PVM_SPEC = importlib.util.spec_from_loader("pvm", _PVM_LOADER)
assert _PVM_SPEC is not None
pvm = importlib.util.module_from_spec(_PVM_SPEC)
_PVM_LOADER.exec_module(pvm)


class TestParser(unittest.TestCase):
    def test_parser_builds(self) -> None:
        self.assertIsNotNone(pvm.build_parser())

    def test_env_template_is_optional(self) -> None:
        parsed = pvm.build_parser().parse_args(["env"])
        self.assertEqual(parsed.subcommand, "env")
        self.assertIsNone(parsed.template)

    def test_init_requires_a_template(self) -> None:
        self.assertEqual(pvm.build_parser().parse_args(["init", "claude"]).template, "claude")
        with self.assertRaises(SystemExit):
            pvm.build_parser().parse_args(["init"])

    def test_runtime_default_and_choices(self) -> None:
        self.assertEqual(pvm.build_parser().parse_args(["list"]).runtime, "crun")
        pvm.build_parser().parse_args(["--runtime", "libkrun", "list"])
        with self.assertRaises(SystemExit):
            pvm.build_parser().parse_args(["--runtime", "bogus", "list"])

    def test_network_passthrough(self) -> None:
        self.assertEqual(pvm.build_parser().parse_args(["--network", "host", "run", "claude"]).network, "host")


class TestDistroFamily(unittest.TestCase):
    def test_known_families(self) -> None:
        self.assertEqual(pvm.distro_family_of_image("debian:13"), "Debian")
        self.assertEqual(pvm.distro_family_of_image("ubuntu:24.04"), "Debian")
        self.assertEqual(pvm.distro_family_of_image("opensuse/tumbleweed"), "Suse")
        self.assertEqual(pvm.distro_family_of_image("fedora:43"), "RedHat")

    def test_unsupported_base_is_none(self) -> None:
        self.assertIsNone(pvm.distro_family_of_image("alpine:3.20"))


class TestProjectName(unittest.TestCase):
    def test_relative_to_home_slug(self) -> None:
        home = Path("/home/u")
        self.assertEqual(pvm.project_name_from_cwd(Path("/home/u/work/proj"), home), "work-proj")

    def test_dotdir_and_odd_chars(self) -> None:
        home = Path("/home/u")
        self.assertEqual(pvm.project_name_from_cwd(Path("/home/u/.config/foo"), home), "config-foo")

    def test_outside_home(self) -> None:
        self.assertEqual(pvm.project_name_from_cwd(Path("/data/x"), Path("/home/u")), "data-x")


class TestCwdMount(unittest.TestCase):
    def test_plain_name(self) -> None:
        self.assertEqual(pvm.cwd_mount(Path("/home/u/proj")).name, "proj")

    def test_dotdir_basename_rewritten(self) -> None:
        self.assertEqual(pvm.cwd_mount(Path("/home/u/.secret")).name, "_secret")

    def test_workspace_workdir(self) -> None:
        m = pvm.Mount(host=Path("/h/proj"), name="proj")
        self.assertEqual(pvm.workspace_workdir([m]), "/workspaces/proj")
        self.assertEqual(pvm.workspace_workdir([m, pvm.Mount(Path("/h/x"), "x")]), "/workspaces")


class TestRunArgv(unittest.TestCase):
    def _argv(self, runtime: str = "crun", network: str | None = "host") -> list[str]:
        return pvm.build_podman_run_argv(
            image_ref="localhost/pvm/claude:abc123",
            container_name="pvm-claude-proj",
            template_name="claude",
            mounts=[pvm.Mount(host=Path("/home/u/proj"), name="proj")],
            hide_dirs=[".git", ".vscode"],
            publish_ports=["1455:1455/tcp"],
            runtime=runtime, network=network)

    def test_core_flags(self) -> None:
        argv = self._argv()
        self.assertEqual(argv[:2], ["podman", "run"])
        self.assertIn("--userns=keep-id", argv)
        self.assertEqual(argv[-1], "localhost/pvm/claude:abc123")
        self.assertIn("--volume", argv)
        self.assertIn("/home/u/proj:/workspaces/proj", argv)
        # hide-dir masks reference the empty MASK_DIR, read-only.
        self.assertTrue(any(f":/workspaces/proj/.git:ro" in a for a in argv))
        self.assertTrue(any(f":/workspaces/proj/.vscode:ro" in a for a in argv))
        self.assertIn("1455:1455/tcp", argv)
        self.assertIn(f"{pvm.LABEL_PROJECT_DIR}=/home/u/proj", argv)

    def test_runtime_mapping(self) -> None:
        self.assertIn("crun", self._argv(runtime="crun"))
        self.assertIn("krun", self._argv(runtime="libkrun"))  # libkrun -> podman krun handler

    def test_network_omitted_when_none(self) -> None:
        self.assertNotIn("--network", self._argv(network=None))
        self.assertIn("--network", self._argv(network="host"))


class TestSchemaAndTemplates(unittest.TestCase):
    """Point the module's template/schema paths at the in-repo files and load them."""

    def setUp(self) -> None:
        pvm.TEMPLATES_DIR = Path(_THIS_DIR) / "templates"
        pvm.SCHEMA_PATH = Path(_THIS_DIR) / "template.schema.json"

    def test_schema_is_valid_json(self) -> None:
        schema = json.loads((Path(_THIS_DIR) / "template.schema.json").read_text())
        self.assertEqual(schema["type"], "object")
        self.assertIn("template_name", schema["required"])

    def test_shipped_templates_load(self) -> None:
        for template_name in ("claude", "codex"):
            doc = pvm.load_template(template_name)
            self.assertEqual(doc["template_name"], template_name)
            self.assertEqual(pvm.distro_family_of_image(doc["image_name"]), "Debian")

    def test_missing_required_field_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            pvm.validate_template({"description": "no name/image"}, "bad")

    def test_unknown_template_dies(self) -> None:
        with self.assertRaises(SystemExit):
            pvm.load_template("does-not-exist")


class TestNewSubcommandsParse(unittest.TestCase):
    """The ivm-aligned subcommands parse (argparse acceptance only; no podman)."""

    def _sub(self, *argv: str) -> object:
        return pvm.build_parser().parse_args(list(argv))

    def test_no_arg_container_subcommands(self) -> None:
        for name in ("info", "update", "reboot", "delete", "overwrite-dotfiles", "start", "stop", "agent"):
            self.assertEqual(self._sub(name).subcommand, name)

    def test_shell_aliases_parse(self) -> None:
        for name in ("shell", "sh", "shell-user", "sh-user", "shell-root", "sh-root",
                     "zsh-user", "zsh-root", "bash-user", "bash-root"):
            self.assertEqual(self._sub(name).subcommand, name)

    def test_reboot_delete_yes_flag(self) -> None:
        self.assertTrue(self._sub("reboot", "--yes").yes)
        self.assertFalse(self._sub("delete").yes)

    def test_push_args(self) -> None:
        parsed = self._sub("push", "/host/f", "/guest/f", "--as-root")
        self.assertEqual((parsed.local, parsed.guest, parsed.as_root), ("/host/f", "/guest/f", True))

    def test_resize_flags(self) -> None:
        parsed = self._sub("resize", "--cpu", "2", "--memory", "4g")
        self.assertEqual((parsed.cpu, parsed.memory), ("2", "4g"))

    def test_provision_units_optional(self) -> None:
        self.assertEqual(self._sub("provision").units, [])
        self.assertEqual(self._sub("provision", "tools_basic", "claude").units, ["tools_basic", "claude"])

    def test_top_passthrough_after_double_dash(self) -> None:
        self.assertEqual(self._sub("top").stats_args, [])
        self.assertEqual(self._sub("top", "--", "--no-stream", "x").stats_args, ["--no-stream", "x"])

    def test_mount_is_two_level_and_requires_action(self) -> None:
        self.assertEqual(self._sub("mount", "ls").mount_action, "ls")
        with self.assertRaises(SystemExit):
            self._sub("mount")  # the action is required


class TestShellSubcommands(unittest.TestCase):
    def test_user_shells_are_zsh_nonroot(self) -> None:
        for name in ("shell", "sh", "shell-user", "sh-user", "zsh-user"):
            self.assertEqual(pvm.SHELL_SUBCOMMANDS[name], ("zsh", False))

    def test_root_shells(self) -> None:
        for name in ("shell-root", "sh-root", "zsh-root"):
            self.assertEqual(pvm.SHELL_SUBCOMMANDS[name], ("zsh", True))
        self.assertEqual(pvm.SHELL_SUBCOMMANDS["bash-root"], ("bash", True))


class TestInfoFormatters(unittest.TestCase):
    """The pure `info` field formatters (inspect dict -> display string)."""

    def test_cpu_limit(self) -> None:
        self.assertEqual(pvm._container_cpu_limit({"NanoCpus": 0}), "(host default)")
        self.assertEqual(pvm._container_cpu_limit({"NanoCpus": 2_000_000_000}), "2")

    def test_memory_limit(self) -> None:
        self.assertEqual(pvm._container_memory_limit({"Memory": 0}), "(host default)")
        self.assertEqual(pvm._container_memory_limit({"Memory": 512 * 1024 * 1024}), "512M")
        self.assertEqual(pvm._container_memory_limit({"Memory": 4 * 1024 ** 3}), "4G")

    def test_published_ports(self) -> None:
        self.assertEqual(pvm._container_published_ports({"PortBindings": {}}), "(none)")
        ports = {"1455/tcp": [{"HostIp": "0.0.0.0", "HostPort": "1455"}]}
        self.assertEqual(pvm._container_published_ports({"PortBindings": ports}), "0.0.0.0:1455->1455/tcp")

    def test_mount_lines_placeholder_and_mask(self) -> None:
        self.assertEqual(pvm._container_mount_lines({"Mounts": []}), ["(none)"])
        mounts = [{"Source": "/h/proj", "Destination": "/workspaces/proj", "RW": True},
                  {"Source": str(pvm.MASK_DIR), "Destination": "/workspaces/proj/.git", "RW": False}]
        lines = pvm._container_mount_lines({"Mounts": mounts})
        self.assertEqual(lines[0], "/h/proj -> /workspaces/proj")
        self.assertIn("[ro] (mask)", lines[1])


if __name__ == "__main__":
    unittest.main()
