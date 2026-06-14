# roles/container_apps/

Installs the **`capp`** launcher(s) for containerized desktop apps (rootless podman),
from a declarative manifest.

- **Type**: face role - `make apply-container-apps` (playbook `container_apps.yml`)
- **Deploys**: launcher script + bash/zsh completions + manifest ->
  `~/.local/share/ansible-managed/container-apps/`
- **State**: `container_apps_state: present | absent` (uninstall = `absent`)
- [Phase 3: folds with `container_templates` into `vm_podman` / `pvm`]
