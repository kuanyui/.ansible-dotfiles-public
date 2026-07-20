# roles/provision_thirdparty_software

Registry of **non-distro install recipes** - the sibling of `roles/provision_distro_packages`
for everything that is NOT an `apt`/`zypper`/`dnf` package name: 3rd-party repos
(vscode), `curl|bash` installers (agent_claude), npm/pip globals (agent_codex).

Data-only role (ships no tasks). `roles/_shared_prebuilt_provision_assets` (invoked from
`roles/vm_incus`'s apply) materializes this registry to `thirdparty-software.json`;
`ivm` reads it and runs the recipes in a guest via `incus exec` when a template lists
them under `thirdparty_software:`, or on demand via `ivm provision <name>`. A host-side
executor can be added later if a host playbook ever needs these.

## Entry shape

Each `provision_thirdparty_software_<name>` is a per-`ansible_os_family` dict. Resolution is
**OVERRIDE, not additive** (UNLIKE `provision_distro_packages`, which concatenates `__common__`
+ the family overlay): a piece of software has one install method, maybe varying
by family - so use the family's entry if defined, else `__common__`.

Inside each family overlay:

| key | required | meaning |
|-----|----------|---------|
| `install_script` | yes | shell run as ROOT in the guest; `su - user -c '...'` for user-scoped installs |
| `already_installed` | no | probe run as root; rc 0 = skip (idempotency). Omit = always run. Prefer a check that only succeeds when truly installed (a file test beats `command -v` when the bin dir is off the login PATH) |

At the entry's TOP level (sibling of the family overlays):

| key | required | meaning |
|-----|----------|---------|
| `distro_packages` | no | distro packages the recipe hard-requires. Installed via the family's package manager BEFORE any recipe runs, on BOTH paths (`ivm init` merges them into the template's package install, `ivm provision <name>` into its batch) - templates never re-list a recipe's deps. Bundle-shaped and ADDITIVE (`__common__` + family overlay) - the one additive field in this registry |

```yaml
provision_thirdparty_software_agent_claude:    # curl|bash installer, same on every distro
  __common__:
    already_installed: su - user -c 'command -v claude'
    install_script: |
      su - user -c 'curl -fsSL https://claude.ai/install.sh | bash'

provision_thirdparty_software_agent_codex:     # npm global, self-carried distro deps
  distro_packages:
    __common__: [nodejs, npm]
  __common__:
    already_installed: su - user -c 'test -x ~/.centralized-lang-pkgs/npm/bin/codex'
    install_script: |
      su - user -c '. ~/.centralized-lang-pkgs/centralized-lang-pkgs.env.sh && npm install -g @openai/codex'

provision_thirdparty_software_vscode:          # 3rd-party repo, per-family (illustrative)
  Debian:
    already_installed: command -v code
    install_script: |
      # ... add the vendor signing key + apt repo, then: apt-get install --yes code
  Suse:
    already_installed: command -v code
    install_script: |
      # ... rpm --import the key + zypper ar the repo, then: zypper --non-interactive install code
```

Write a repo recipe to ADD THE REPO (not fetch a one-off package file), so `ivm
update` (apt/zypper upgrade) keeps it current.

## Adding a recipe

1. Define `provision_thirdparty_software_<name>` in `defaults/main.yml`; declare any distro
   prerequisites in its `distro_packages` (NO paired same-named distro bundle - that
   convention is gone).
2. Add it to the render dict in `roles/_shared_prebuilt_provision_assets/tasks/main.yml`
   (`thirdparty-software.json`) - same explicit-list pattern as the distro bundles.
3. Reference it from a template's `thirdparty_software: [<name>]`, or install ad-hoc with
   `ivm provision <name>`.
