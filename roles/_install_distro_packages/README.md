# roles/_install_distro_packages/

Distro-aware package installer, **ansible-core only** (shells `apt`/`zypper`/`dnf`
directly - dodges `ansible.builtin.package` -> `community.general.zypper` on openSUSE).

- **Type**: internal `_` utility - `include_role` only (no playbook / target)
- **Input** `install_distro_packages`: dict keyed by `ansible_os_family`
  (`Debian`/`Suse`/`RedHat`), each `{ install: [pkgs], probe: <shell, optional> }`
- **`probe`**: rc 0 -> skip install (idempotency). Omitted -> always install.
- **Used by**: `provision` (host bundle installs) + `vm_incus` (its own host deps)
- Host's `os_family` missing from the dict -> fails loud (caller didn't declare support)
