"""What the `backup` / `restore` scripts share: the target VM's template `backup:` block
(template.schema.json) resolved from the `ivm script` env, the tar commands, and the
host backup-dir listing. `_`-prefixed = a library, not a runnable script."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _ivm_script_lib import die, guest_exec_command, host_downloads_dir, ivm_env  # noqa: E402

BACKUP_BLOCK_REQUIRED_KEYS: tuple[str, ...] = ("unit", "dir", "paths", "host_downloads_subdir")


class BackupSpec(NamedTuple):
    """A template's `backup:` block, resolved for one VM."""
    vm_name: str
    template_name: str
    unit: str                 # per-user systemd unit stopped around the tar
    dir: str                  # absolute guest dir tar runs in (`tar --directory`)
    paths: list[str]          # what to tar, relative to `dir`
    podman_unshare: bool      # wrap tar in `podman unshare` (rootless-podman-owned data)
    host_backups_dir: Path    # <host XDG DOWNLOAD dir>/<host_downloads_subdir>


def load_backup_spec() -> BackupSpec:
    """The target VM's `backup:` block, read LIVE from its template - `IVM_TEMPLATE_FILE`,
    the file named by the VM's `user.ivm_template` tag (the same live read as `ivm info`'s
    Usage group) - so a fix in the template applies to every existing VM. Dies naming the
    missing link when the tag, the file, the block or one of its keys is absent."""
    import yaml  # an ivm host dependency (python3-yaml), lazy so a missing dep reads clearly
    vm_name: str = ivm_env("IVM_VM")
    template_name: str = ivm_env("IVM_TEMPLATE")
    if not template_name:
        die(f"{vm_name} has no `user.ivm_template` tag, so its template's `backup:` block cannot "
            f"be looked up (a hand-made VM? `ivm --name {vm_name} adopt` sets the tag)")
    template_file: Path = Path(ivm_env("IVM_TEMPLATE_FILE"))
    if not template_file.is_file():
        die(f"template file not found: {template_file} (the VM's `user.ivm_template` tag names "
            f"'{template_name}')")
    template_doc: Any = yaml.safe_load(template_file.read_text()) or {}
    backup_block: Any = template_doc.get("backup") if isinstance(template_doc, dict) else None
    if not isinstance(backup_block, dict) or not backup_block:
        die(f"template '{template_name}' declares no `backup:` block - nothing says what to back "
            f"up (add one: unit / dir / paths / host_downloads_subdir - see template.schema.json)")
    for required_key in BACKUP_BLOCK_REQUIRED_KEYS:
        if required_key not in backup_block:
            die(f"template '{template_name}' `backup:` block lacks `{required_key}` (see template.schema.json)")
    return BackupSpec(
        vm_name=vm_name,
        template_name=template_name,
        unit=str(backup_block["unit"]),
        dir=str(backup_block["dir"]),
        paths=[str(path) for path in backup_block["paths"]],
        podman_unshare=bool(backup_block.get("podman_unshare", False)),
        host_backups_dir=host_downloads_dir() / str(backup_block["host_downloads_subdir"]),
    )


def describe_backup_targets(spec: BackupSpec) -> str:
    """`/home/user/SillyTavern/{data, config.yaml}` - what a backup covers, for messages."""
    return f"{spec.dir}/{{{', '.join(spec.paths)}}}"


def backup_tar_command(spec: BackupSpec, tar_mode_args: list[str]) -> list[str]:
    """The host command that streams a tar of `spec.paths` out of (`--create`) or into
    (`--extract`) the guest as `user`, inside `podman unshare` when the block says so."""
    tar_argv: list[str] = ["tar", "--directory", spec.dir, *tar_mode_args]
    if spec.podman_unshare:
        tar_argv = ["podman", "unshare", *tar_argv]
    return guest_exec_command(spec.vm_name, tar_argv)


def backup_tars_newest_first(host_backups_dir: Path) -> list[Path]:
    """Every `*.tar` in the VM's backup dir, newest mtime first - the tars the OLD in-guest
    `llm-backup` wrote (`STBackup_*` etc.) included, so `latest` and the listing cover them."""
    if not host_backups_dir.is_dir():
        return []
    return sorted((tar_path for tar_path in host_backups_dir.glob("*.tar") if tar_path.is_file()),
                  key=lambda tar_path: tar_path.stat().st_mtime, reverse=True)
