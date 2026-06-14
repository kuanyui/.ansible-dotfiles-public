# roles/zsh/

Deploys `~/.zshrc` (the login shell) + installs the `zsh` package when `is_root`.

- **Deploys**: `.zshrc` - shared snippets (`shared_*`) from `roles/_shared_j2_snippets`;
  `override_os_family` picks the per-distro min-install helper (apt-min / zypper-min / dnf-min)
- **Invoked by**: `include_role` - essentials (`playbooks/user.yml`) + `vm_incus` dotfiles staging
- **Caller sets**: `target_home` / `target_user` / `target_group` / `is_root` (+ optional `override_os_family`)
