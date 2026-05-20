"""Sandbox config for `playbooks/container_apps.yml`.

Installs `c-<template>-<runtime>` launchers + completions + the rendered
`container-templates/` tree under `~/.local/share/ansible-managed/`. Pure file
deployment - the role doesn't actually invoke `podman` at install time, so we
don't need the binary inside the sandbox.

The playbook sets `setup_container_apps: true` itself (it's the dedicated
entry point that bypasses the host-level opt-in gate), so no `extra_ansible_vars`
override needed here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import SandboxConfig  # noqa: E402


CONFIG = SandboxConfig(
    name="container_apps",
    description="c-<template>-<runtime> launcher + completion + manifest deployment.",
    playbook=Path("playbooks/container_apps.yml"),
)
