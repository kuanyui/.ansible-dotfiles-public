# roles/emacs/

Deploys the `~/.emacs.d` config + installs the `emacs` package (when `is_root`).

- **Deploys**: static + templated `.emacs.d` tree (distro-independent)
- **Invoked by**: `include_role` - essentials (`playbooks/user.yml`) + `vm_incus` (`ivm provision emacs`) staging
- **Caller sets**: `target_home` / `target_user` / `target_group` / `is_root`
- `is_root: true` also installs the distro `emacs` package
