# roles/container_templates/

Renders **podman image-build assets** from declarative container templates: a
`Dockerfile` + per-user `.bashrc` / `.zshrc` + a host CLI + per-template README.

- **Invoked by**: playbook `playbooks/container_templates.yml` (no `make` target); guests
  inside the `container-apps/` subdir (utility role - no top-level subdir of its own)
- **Renders**: `Dockerfile` + dotfiles + `host-cli.sh` per template
- Validates each template's `nodejs` block (`install_via: distro | nvm | none`)
- [Phase 3: folds with `container_apps` into `vm_podman` / `pvm`]
