# roles/provision/

**The provisioning registry** - what gets installed on hosts and into `ivm` / `qvm` / `pvm`
guests. One role, two registries under `defaults/main/` (ansible loads every file in that
directory). Each registry is ONE dict variable; entries are its keys (short names - dict
keys, unlike top-level vars, cannot collide with other roles' variables):

| registry | file | entries |
|----------|------|---------|
| distro-package bundles | `defaults/main/distro_packages.yml` | `provision_distro_packages.<bundle>` |
| non-distro install recipes | `defaults/main/thirdparty_software.yml` | `provision_thirdparty_software.<name>` |

Consumers:

- **Host install** (bundles only): `tasks/main.yml` installs the bundles toggled on by
  `provision_distro_packages_install_*` (flat vars ON PURPOSE - a host_var can flip one
  toggle without redeclaring a dict), via `roles/_install_distro_packages`. Recipes have
  no host-side executor yet - add one if a host playbook ever needs them.
- **Guest / container**: `roles/_shared_prebuilt_provision_assets` serializes both
  registry dicts VERBATIM to `distro-package-groups.json` + `thirdparty-software.json`;
  `ivm` / `qvm` / `pvm` read them (`ivm provision <name>`, template `packages:` /
  `thirdparty_software:` lists). Launcher completions auto-track the JSONs - no
  completion edit needed.

## `available_on` - per-consumer visibility

Any entry (bundle or recipe) MAY carry `available_on: [<consumer>, ...]` with consumers
from `host` / `ivm` / `qvm` / `pvm`. ABSENT = available to every consumer (the normal
case). Enforcement, per side:

- each launcher's registry loader (and its shell completions) drops entries whose
  `available_on` excludes it - they neither resolve nor complete
- the host toggle loop (`tasks/main.yml`) asserts every enabled bundle lists `host`
  (or omits the field)

Example: the `dev_android` BUNDLE is `available_on: [host]` - guests get the same deps
from the `dev_android` RECIPE's `distro_packages`, so the bundle would only shadow the
recipe's completion description.

## Distro-package bundles (`defaults/main/distro_packages.yml`)

Named bundles (`tools_basic`, `gui_x11`, `cjk_input`, `desktop_lxqt`, ...), each a
per-`ansible_os_family` overlay. Resolution is **ADDITIVE**: `__common__` + the family's
overlay (`Debian` / `Suse` / `RedHat`).

## Non-distro recipes (`defaults/main/thirdparty_software.yml`)

Everything that is NOT an `apt`/`zypper`/`dnf` package name: 3rd-party repos (vscode),
`curl|bash` installers (agent_claude), npm/pip globals (agent_codex).

Each entry is a per-`ansible_os_family` dict. Resolution is **OVERRIDE, not additive**
(UNLIKE bundles): a piece of software has one install method, maybe varying by family -
so use the family's entry if defined, else `__common__`.

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
provision_thirdparty_software:
  agent_claude:      # curl|bash installer, same on every distro
    __common__:
      already_installed: su - user -c 'command -v claude'
      install_script: |
        su - user -c 'curl -fsSL https://claude.ai/install.sh | bash'

  agent_codex:       # npm global, self-carried distro deps
    distro_packages:
      __common__: [nodejs, npm]
    __common__:
      already_installed: su - user -c 'test -x ~/.centralized-lang-pkgs/npm/bin/codex'
      install_script: |
        su - user -c '. ~/.centralized-lang-pkgs/centralized-lang-pkgs.env.sh && npm install -g @openai/codex'

  vscode:            # 3rd-party repo, per-family (illustrative)
    Debian:
      already_installed: command -v code
      install_script: |
        # ... add the vendor signing key + apt repo, then: apt-get install --yes code
    Suse:
      already_installed: command -v code
      install_script: |
        # ... rpm --import the key + zypper ar the repo, then: zypper --non-interactive install code
```

Write a repo recipe to ADD THE REPO (not fetch a one-off package file), so `ivm update`
(apt/zypper upgrade) keeps it current.

## Adding a bundle / recipe

1. Define the entry under `provision_distro_packages` / `provision_thirdparty_software` in
   the matching `defaults/main/*.yml` - that is the whole job (the JSON serialization and
   the launcher completions pick it up automatically). A recipe declares its distro
   prerequisites in its own `distro_packages` (NO paired same-named distro bundle - that
   convention is gone). Add `available_on` only to restrict consumers.
2. Bundles on HOSTS additionally need a `provision_distro_packages_install_<bundle>` toggle
   (flat var + the toggle loop in `tasks/main.yml`). Recipes are referenced from a
   template's `thirdparty_software: [<name>]` or run ad-hoc via `ivm provision <name>`.
