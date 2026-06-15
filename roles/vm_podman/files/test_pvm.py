#!/usr/bin/env python3
"""Unit tests for `pvm`'s pure helpers.

Sub-phase 3.0 scaffold: only the argument parser + a few helpers exist, so the
tests cover the CLI surface. Richer pure-function tests (distro mapping, mount
parsing, podman argv, content hash) land with sub-phases 3.1-3.2.

Run:  cd roles/vm_podman/files && python3 -m unittest test_pvm -v
"""

import importlib.util
import os
import unittest
from importlib.machinery import SourceFileLoader

# `pvm` is an extensionless executable, so name the loader explicitly (the
# default spec resolution only recognizes .py). Same trick as test_qvm.py.
_THIS_DIR: str = os.path.dirname(os.path.abspath(__file__))
_PVM_LOADER = SourceFileLoader("pvm", os.path.join(_THIS_DIR, "pvm"))
_PVM_SPEC = importlib.util.spec_from_loader("pvm", _PVM_LOADER)
assert _PVM_SPEC is not None
pvm = importlib.util.module_from_spec(_PVM_SPEC)
_PVM_LOADER.exec_module(pvm)


class TestParser(unittest.TestCase):
    """The CLI surface must parse the way the dispatcher + completions expect."""

    def test_parser_builds(self) -> None:
        self.assertIsNotNone(pvm.build_parser())

    def test_env_template_is_optional(self) -> None:
        parsed = pvm.build_parser().parse_args(["env"])
        self.assertEqual(parsed.subcommand, "env")
        self.assertIsNone(parsed.template)

    def test_init_requires_a_template(self) -> None:
        parsed = pvm.build_parser().parse_args(["init", "claude"])
        self.assertEqual(parsed.subcommand, "init")
        self.assertEqual(parsed.template, "claude")
        with self.assertRaises(SystemExit):
            pvm.build_parser().parse_args(["init"])  # missing required template

    def test_runtime_defaults_to_crun(self) -> None:
        self.assertEqual(pvm.build_parser().parse_args(["list"]).runtime, "crun")

    def test_runtime_choices_are_enforced(self) -> None:
        pvm.build_parser().parse_args(["--runtime", "libkrun", "list"])  # valid
        with self.assertRaises(SystemExit):
            pvm.build_parser().parse_args(["--runtime", "bogus", "list"])

    def test_container_acting_subcommands_take_no_positional(self) -> None:
        for subcommand in ("start", "stop", "rmc", "rmi", "rma", "shell", "agent"):
            parsed = pvm.build_parser().parse_args([subcommand])
            self.assertEqual(parsed.subcommand, subcommand)


if __name__ == "__main__":
    unittest.main()
