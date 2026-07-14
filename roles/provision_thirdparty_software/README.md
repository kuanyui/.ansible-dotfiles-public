# roles/provision_thirdparty_software

Registry of **non-distro install recipes** - the sibling of `roles/provision_distro_packages`
for everything that is NOT an `apt`/`zypper`/`dnf` package name: 3rd-party repos
(vscode), vendor install scripts (agent_claude, agent_codex), npm/pip globals.

Data-only role (ships no tasks). `roles/vm_incus` materializes this registry to
`thirdparty-software.json` at apply time; `ivm` reads it and runs the recipes in a
guest via `incus exec` when a template lists them under `thirdparty_software:`. A
host-side executor can be added later if a host playbook ever needs these.

## Entry shape

Each `provision_thirdparty_software_<name>` is a per-`ansible_os_family` dict. Resolution is
**OVERRIDE, not additive** (UNLIKE `provision_distro_packages`, which concatenates `common`
+ the family overlay): a piece of software has one install method, maybe varying
by family - so use the family's entry if defined, else `common`.

| key | required | meaning |
|-----|----------|---------|
| `install_script` | yes | shell run as ROOT in the guest; `su - user -c '...'` for user-scoped installs |
| `already_installed` | no | probe run as root; rc 0 = skip (idempotency). Omit = always run. Prefer a check that only succeeds when truly installed (a file test beats `command -v` when the bin dir is off the login PATH) |

```yaml
provision_thirdparty_software_agent_claude:    # curl|bash installer, same on every distro
  common:
    already_installed: su - user -c 'command -v claude'
    install_script: |
      su - user -c 'curl -fsSL https://claude.ai/install.sh | bash'

provision_thirdparty_software_vscode:          # 3rd-party repo, per-family (illustrative)
  debian:
    already_installed: command -v code
    install_script: |
      # ... add the vendor signing key + apt repo, then: apt-get install -y code
  suse:
    already_installed: command -v code
    install_script: |
      # ... rpm --import the key + zypper ar the repo, then: zypper -n install code
```

Write a repo recipe to ADD THE REPO (not fetch a one-off package file), so `ivm
update` (apt/zypper upgrade) keeps it current.

## Migrating an old VM off the npm-installed `codex`

`agent_codex` used to be `npm install -g @openai/codex`; it is now the official standalone
installer (no nodejs/npm). A VM provisioned by the OLD recipe keeps its npm copy, and that
copy **wins on PATH** - so the new one looks installed but never runs:

| copy | path | how it reaches PATH |
|------|------|---------------------|
| old (npm) | `~/.centralized-lang-pkgs/npm/bin/codex` | env file, **prepended** |
| new (standalone) | `~/.local/bin/codex` | `.zshrc`, **appended** |

Remove the old one in the guest, then re-provision:

```
npm uninstall -g @openai/codex
```

Not automated on purpose - the recipe never removes software it did not install this run.
`which codex` should then print `~/.local/bin/codex`. (A VM built fresh from the `codex`
template is unaffected - it has no npm at all.)

## Adding a recipe

1. Define `provision_thirdparty_software_<name>` in `defaults/main.yml`.
2. Add it to the render list in `roles/vm_incus/tasks/ivm_install.yml`
   (`thirdparty-software.json`) - same explicit-list pattern as the distro bundles.
3. Reference it from a template's `thirdparty_software: [<name>]`.
