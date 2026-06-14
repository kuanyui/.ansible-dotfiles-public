# roles/bash/

Deploys `~/.bashrc` (config-only; one role per shell, like `zsh` / `tmux`).

- **Deploys**: `.bashrc` - root gets a trimmed variant (`is_root`)
- **Invoked by**: `include_role` from `playbooks/{user,root}.yml` + `vm_incus` dotfiles staging (no standalone playbook)
- **Caller sets**: `target_home` / `target_user` / `target_group` / `is_root`
- Drops in shared snippets (`shared_*`) from `roles/_shared_j2_snippets`
