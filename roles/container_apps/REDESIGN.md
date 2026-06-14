# container_apps redesign - one engine + declarative templates (parallel to `ivm`)

Status: DESIGN / not started. This mirrors what `roles/vm_incus` did to the old
`incus_agents` bash launchers, applied to the podman side.

> **Naming is OPEN.** This doc uses `capp` as a *working name only* for the
> single launcher binary - final name TBD (candidates: `capp` / `cax` / `coci`).
> `s/capp/<final>/` once decided.

## Why redesign

The podman feature is the SAME shape `ivm` just replaced on the incus side: many
rendered-per-entry bash launchers + a manifest, with guest dotfiles maintained
separately from `roles/zsh`.

Current pieces:

| Piece | What it is |
| --- | --- |
| `roles/container_templates` | Renders, per template: `Dockerfile.j2` (+ a systemd flavor for krun), **`host-cli.sh.j2` - a 454-line Jinja-templated bash CLI**, `bashrc.j2` / `zshrc.j2` (own dotfiles, baked into the image), `README.md.j2`. Output -> `container-apps/container-templates/<name>/`. |
| `roles/container_apps` | Renders a thin `c-<template>-<runtime>` launcher (sets `RUNTIME`, `exec`s `host-cli.sh`) per `(template, runtime)`, + zsh/bash completions, + a manifest. |
| `filter_plugins/distro.py` | image tag -> distro family (ported byte-identical from a legacy `render_j2.py`). |

Problems (the same ones `ivm` fixed):

1. **Logic lives in templated bash.** A 454-line `host-cli.sh.j2` (build / run /
   mount-interpolation / runtime selection / userns / ports / rm) is Jinja-in-bash:
   hard to test, hard to read, "byte-identical port from legacy render_j2.py".
2. **N launchers + manifest.** One launcher per `(template, runtime)` + a manifest
   to track them for uninstall - exactly the model `ivm` dropped for cwd-resolution.
3. **Duplicated dotfiles.** `container_templates` ships its OWN `zshrc.j2` /
   `bashrc.j2` (~130 lines, only partly sharing `_shared_j2_snippets` fragments) instead of
   reusing `roles/zsh` like `ivm`'s dotfiles staging does. The only genuinely
   container-specific bit is "auto-cd into `/workspaces/*` on login".
4. **Split role, single consumer.** `container_templates` is consumed only by
   `container_apps` (via `include_role`) - same fold-in candidate as the former
   `_incus_*` roles.

## Target (parallel to `ivm`)

ONE Python program (`capp`, working name) that reads declarative YAML container
templates and drives podman from the host. It subsumes:

- the thin `c-<template>-<runtime>` launchers + `_launcher.{bash,zsh}.j2` + manifest,
- the 454-line `host-cli.sh.j2` (build/run/lifecycle in testable Python),
- `container_templates`'s render step (folded into the engine role).

And reuses `roles/zsh` for guest dotfiles (stage host-side like
`roles/vm_incus/tasks/stage_dotfiles.yml`, then `COPY` into the image), with a
small container-only overlay for the `/workspaces` auto-cd.

## NOT a copy of `ivm` - real differences

Containers are a different shape from VMs; the engine is parallel, not shared:

| Aspect | `ivm` (incus VM) | `capp` (podman container) |
| --- | --- | --- |
| Lifecycle | persistent VM, `incus create`/`start` | ephemeral container, `podman build` then `podman run` |
| Image | pull `images:debian/13` | **build from a Dockerfile** (per template) |
| Dotfiles delivery | `incus file push` at init (runtime) | **`COPY` into the image at build** |
| Runtime variants | n/a | **`crun` (lightweight) vs `krun` (microVM; needs systemd-as-PID1 Dockerfile flavor)** |
| Identity | one VM per dir (`user.ivm_init_at_dir`) | one container per `(template, runtime, project)`, name `c-<tpl>-<rt>-<proj>` |
| Isolation extras | virtio-fs `shift=true` | userns UID mapping, `--mount`, `--publish` ports |

So this is a SECOND engine, sharing patterns (declarative templates, reuse
`roles/zsh`, dry-run, fold helper roles in) but not code.

## Declarative template schema (mostly already exists)

`container_templates`' entries are already declarative - reuse the schema, add a
JSON Schema + LSP modeline like `ivm`. Fields seen today:

- `name`, `image_name` (-> distro family via the filter), `image_platform`, `tz`
- `distro_pkgs[]`, `feature_presets[]` (`zsh`, `qemacs`, ...)
- `nodejs: {install_via: distro|nvm|none, npm_global_pkgs[]}`
- `install_script_url` (curl-installed agent, e.g. claude)
- `agent: {target_suffix, command, display_name, auth_note}`
- `publish_ports[]`, and runtime mounts (`--mount`, interpolation)
- runtimes per app: `[crun, krun]` (currently in `container_apps`)

Open: whether to keep `Dockerfile.j2` (engine renders it) or generate the
Dockerfile inline in Python. Leaning keep-the-template (build context is naturally
a file), engine just fills build-args + picks the crun/krun flavor.

## Subcommand surface (from today's host-cli.sh)

`capp <subcommand>` (cwd-resolved where it makes sense):
`init` (= build + run), `build`, `run`, `start`, `stop`, `rmc` (rm container),
`rmi` (rm image), `rma` (both), `shell`/`bash-user`/`bash-root`/`zsh-user`/`zsh-root`,
the agent command (`claude` / `codex`), `env`, `help`. Global: `--dry-run`, `--runtime crun|krun`.

## What this resolves

- Q1 (does `container_templates` deserve a separate role?): no - fold its render
  step into the `capp` engine role (single consumer).
- Q2 (own `zshrc.j2`?): no - reuse `roles/zsh` staged output + a container overlay
  (auto-cd). Kills ~130 lines of duplicated dotfiles.
- Q3 (ivm-style?): this whole doc.

## Phases (each independently shippable)

| Phase | Content |
| --- | --- |
| 0 scaffold | `capp` binary + JSON Schema + example templates (claude, codex); `capp env`, `--dry-run`. |
| 1 build + run | `init`/`build`/`run` for crun: render Dockerfile (build-args), `podman build`, `podman run` with mounts/ports/userns; `shell`/agent. |
| 2 krun + lifecycle | systemd-PID1 Dockerfile flavor for krun; start/stop/rmc/rmi/rma. |
| 3 dotfiles unify | stage via `roles/zsh` + container overlay, `COPY` into image; delete `container_templates`'s `zshrc.j2`/`bashrc.j2`. |
| 4 retire | drop the rendered launchers + `host-cli.sh.j2` + manifest + `_launcher.{bash,zsh}.j2`; fold `container_templates` -> engine role; migrate `c-claude-*`/`c-codex-*` to templates. |

## Open decisions

- **Name** (you said TBD): `capp` / `cax` / `coci` / other. Affects the binary,
  the `setup_*` gate, playbook, Makefile targets, sandbox config (full-rename like
  podman_oci_runtimes).
- Dockerfile: engine-rendered template vs Python-generated (leaning: template).
- Image rebuild detection (when does `init` rebuild vs reuse?) - today the marker
  is image presence; keep or add a content hash.
- `filter_plugins/distro.py` -> port into the engine as a plain function.
- Cleanup: committed `filter_plugins/__pycache__/*.pyc` should be `git rm --cached`.
