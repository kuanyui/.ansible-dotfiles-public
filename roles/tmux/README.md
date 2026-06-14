# roles/tmux/

Deploys `~/.tmux.conf` (config-only; static - identical for user + root, so no `is_root`).

- **Invoked by**: `include_role` from `playbooks/{user,root}.yml` + `vm_incus` dotfiles staging (no standalone playbook)
- **Caller sets**: `target_home` / `target_user` / `target_group`
