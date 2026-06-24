# roles/vm_podman - `pvm`, the podman container launcher

Installs `pvm`: a typed-Python wrapper around [podman](https://podman.io) for the
container axis `ivm` (roles/vm_incus) and `qvm` (roles/vm_quickemu) do not cover -
quick per-project app containers (e.g. an AI-agent dev box). Folds the old
`container_apps` + `container_templates` roles into one engine (see
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)).

| | `ivm` (incus) | `qvm` (quickemu) | `pvm` (podman) |
| --- | --- | --- | --- |
| Niche | per-project headless Linux VM | desktop / Windows / macOS | per-project app container |
| Image | incus `images:` remote | prebuilt qcow2 / quickget | built per template (exec + commit) |
| Exec | `incus exec` | QGA + SSH | `podman exec` (crun) |
| Isolation | real VM (own kernel) | real VM (own kernel) | **shared host kernel** (crun) |

## Isolation honesty

pvm's default runtime `crun` shares the HOST kernel - NOT the boundary a real VM
gives. For kernel-level isolation use `ivm`. pvm warns at install and gates
`pvm init` per-container. A `libkrun` microVM runtime is a later addition (see the
plan); until then `--runtime libkrun` is accepted but not yet driven.

## How it works (no Dockerfile)

`pvm init <template>` builds a per-template image by provisioning a base container
via `podman exec` + `podman cp` (packages + thirdparty recipes + dotfiles, all
from the SAME shared provision-asset cache `ivm`/`qvm` use), then `podman commit`s
it - keyed by a content hash so an unchanged template reuses the image. A
per-project container is then run from that image, mounting the cwd.

## Status

Fully wired: the build pipeline (`init` / `build` / `run`), the real podman drive,
the isolation gates, and a management surface aligned with `ivm` (the reference
launcher). `libkrun` (microVM runtime) stays deferred - `--runtime libkrun` is
accepted but not yet driven. See [TODO.md](TODO.md) for the ivm->pvm alignment map
(what ports, what podman cannot do).

## Subcommands

- **build/run**: `init` (build image if needed + run cwd container), `build`, `run`, `env`
- **lifecycle**: `start`, `stop`, `reboot`, `rmc` / `rmi` / `rma`, `delete`
- **enter**: `shell`/`sh`, `shell-user`, `shell-root` (+ `zsh-*` / `bash-*`), `agent`
- **manage**: `info`, `update`, `provision [unit...]`, `overwrite-dotfiles`, `push`, `resize`, `mount ls`, `top`, `list`

podman cannot hot-change a running container's mounts/ports or give it a VM console,
so ivm's `expose` / `mount attach` / `gui` / `snapshot` / `set ssh-server` are NOT
ported (the container's mounts/ports are fixed at `init` from the template; see
[TODO.md](TODO.md)).

## Files

```
roles/vm_podman/
  files/pvm                  the launcher (typed Python, stdlib only)
  files/test_pvm.py          unit tests (pure helpers)
  files/completions/         _pvm (zsh) + pvm.bash
  IMPLEMENTATION_PLAN.md     the phased build plan (durable, in-repo)
  TODO.md                    ivm->pvm subcommand alignment map + status
~/.local/share/ansible-managed/vm-podman/   pvm program data + completions (uninstall = rm -rf)
podman image/container storage              built images/containers (NEVER touched by ansible)
```

## Commands

`make vm-podman-install` / `vm-podman-check` (dry-run) / `vm-podman-uninstall-pvm`
/ `vm-podman-sandbox`.
