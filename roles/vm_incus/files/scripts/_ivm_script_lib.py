"""Shared plumbing for the `ivm script` helper scripts in this directory. `_`-prefixed =
a library, not a runnable script (`ivm script` lists/runs only the un-prefixed files).

The model: a script runs on the HOST, in the caller's cwd, with its args verbatim and the
env `ivm script` sets (names = the SOURCE identifiers, never renamed): `IVM_VM` (the
resolved VM name); every `user.ivm_<tag>` of the VM as `IVM_<TAG>` - `IVM_TEMPLATE`
(always set, empty when untagged), `IVM_HOST_BOUND_DIR`, `IVM_SHELL_DEFAULT_DIR_AFTER_LOGIN`,
`IVM_ANSIBLE_OS_FAMILY`, ... (an absent tag = an absent variable); `IVM_TEMPLATE_FILE` (that
template's path, may not exist); `IVM_PRIMARY_IPV4` (empty without a lease); `IVM_ROOT` +
`SHARED_PREBUILT_PROVISION_ASSETS_ROOT` (the env names ivm itself honors); `IVM_YES` (`1`
under `ivm --yes`) - and drives the guest through `incus exec`; the guest itself runs
nothing on its own, the same model as ivm's own subcommands. Data moves through `incus
exec`'s stdin/stdout, so no virtio-fs share is needed. Import with
`sys.path.insert(0, str(Path(__file__).resolve().parent))`.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# `incus exec` as the unprivileged guest `user` (uid/gid 1000) with the per-user D-Bus env -
# the same patch-up `ivm shell` makes: `incus exec` spawns the process directly (no PAM
# login), so without these `systemctl --user` cannot find the user bus and rootless podman
# cannot find its runtime dir.
GUEST_USER_EXEC_ARGS: tuple[str, ...] = (
    "--user", "1000", "--group", "1000", "--cwd", "/home/user",
    "--env", "HOME=/home/user", "--env", "USER=user",
    "--env", "XDG_RUNTIME_DIR=/run/user/1000",
    "--env", "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
)


def script_name() -> str:
    return Path(sys.argv[0]).name


def die(message: str) -> NoReturn:
    print(f"{script_name()}: error: {message}", file=sys.stderr)
    raise SystemExit(1)


def announce(command: list[str], redirect_note: str = "") -> None:
    """Print a command before it runs (host-side transparency), `+ <cmd>  > <file>` style."""
    print("+ " + shlex.join(command) + (f"  {redirect_note}" if redirect_note else ""), file=sys.stderr)


def ivm_env(variable_name: str) -> str:
    """An `IVM_*` variable `ivm script` sets; dies when it is missing (script run by hand)."""
    value: str | None = os.environ.get(variable_name)
    if value is None:
        die(f"{variable_name} is not set - run this through `ivm --name <vm> script {script_name()}`")
    return value


def assume_yes() -> bool:
    """True under `ivm --yes` (skip confirmation prompts)."""
    return os.environ.get("IVM_YES") == "1"


def capture(command: list[str]) -> str:
    """Run a read-only command and return its stdout ("" on failure)."""
    result: subprocess.CompletedProcess[str] = subprocess.run(command, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def guest_exec_command(vm_name: str, guest_argv: list[str], *, as_root: bool = False) -> list[str]:
    """The host command that runs `guest_argv` inside the VM: as `user` (with the D-Bus env
    above) by default, as root with `as_root`."""
    if as_root:
        return ["incus", "exec", vm_name, "--", *guest_argv]
    return ["incus", "exec", *GUEST_USER_EXEC_ARGS, vm_name, "--", *guest_argv]


def guest_user_unit_is_active(vm_name: str, unit: str) -> bool:
    """`systemctl --user is-active <unit>` inside the guest, as `user`."""
    return capture(guest_exec_command(vm_name, ["systemctl", "--user", "is-active", unit])).strip() == "active"


def guest_user_unit_control(vm_name: str, action: str, unit: str) -> None:
    """`systemctl --user <start|stop> <unit>` inside the guest as `user` (printed first);
    dies when it fails."""
    command: list[str] = guest_exec_command(vm_name, ["systemctl", "--user", action, unit])
    announce(command)
    if subprocess.run(command).returncode != 0:
        die(f"`systemctl --user {action} {unit}` failed in {vm_name}")


def host_downloads_dir() -> Path:
    """The host's XDG DOWNLOAD dir (`xdg-user-dir DOWNLOAD` - what the templates' Downloads
    mounts expand to); `~/Downloads` when the tool is absent."""
    xdg_download_dir: str = capture(["xdg-user-dir", "DOWNLOAD"]).strip()
    return Path(xdg_download_dir) if xdg_download_dir else Path.home() / "Downloads"


def human_size(byte_count: int) -> str:
    """`12.3 KiB` / `45.6 MiB` / `1.2 GiB` - the IEC unit that keeps the number readable."""
    if byte_count < 1048576:
        return f"{byte_count / 1024:.1f} KiB"
    if byte_count < 1073741824:
        return f"{byte_count / 1048576:.1f} MiB"
    return f"{byte_count / 1073741824:.1f} GiB"
