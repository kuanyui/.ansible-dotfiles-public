# roles/provision_thirdparty_software

Registry of **non-distro install recipes** - the sibling of `roles/provision_distro_packages`
for everything that is NOT an `apt`/`zypper`/`dnf` package name: 3rd-party repos
(vscode), `curl|bash` installers (claude), npm/pip globals (codex).

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
provision_thirdparty_software_claude:          # curl|bash installer, same on every distro
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

## Adding a recipe

1. Define `provision_thirdparty_software_<name>` in `defaults/main.yml`.
2. Add it to the render list in `roles/vm_incus/tasks/ivm_install.yml`
   (`thirdparty-software.json`) - same explicit-list pattern as the distro bundles.
3. Reference it from a template's `thirdparty_software: [<name>]`.
