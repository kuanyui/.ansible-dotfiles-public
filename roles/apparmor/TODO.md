# TODO

## `python3-jsonschema` install: handled by the role itself

`roles/apparmor/scripts/gen_personal_dirs_aa_mixins.py` validates
`roles/apparmor/local_vars/personal_dirs.yml` against a JSON Schema at playbook
run time using the `jsonschema` Python package.

Handled by:

- `roles/apparmor/tasks/main.yml`: delegates to the shared sub-role
  `_install_distro_packages` via `ansible.builtin.include_role`. The sub-role
  takes a per-`os_family` dict (Debian / Suse / RedHat) with `install: [...]`
  + optional `probe`; it shells out to `zypper --non-interactive install` on
  openSUSE (because `ansible.builtin.package` would dispatch to
  `community.general.zypper`, violating the ansible-core-only rule) and uses
  `ansible.builtin.apt` / `ansible.builtin.dnf` elsewhere. The probe
  (`python3 -c "import jsonschema"`) gates the install so hosts that already
  have it skip silently. See `roles/_install_distro_packages/tasks/main.yml`
  for the contract.
- `scripts/sandbox/configs/apparmor.py`: `_pre_flight` runs the same probe
  on the host (before any container work) and shells out to the host's
  package manager via `sudo` if missing. `extra_packages_apt` then ensures
  the sandbox container also has it from apt install time.
- `roles/apparmor/CLAUDE.md`: documents the hard dep.

Rule: install the distro package, not via pip. This project uses ansible-core
only and avoids pip-managed Python deps on the target.

## `local_mixin_container_base` still includes deprecated personal_dirs mixin

`files/profiles/local_mixin_container_base.aa` continues to `#include
<abstractions/local_mixin_deny_personal_dirs>` (the deprecated all-or-nothing
mixin). It is consumed by two attachmentless profiles:

- `local_attachmentless_podman_ai_agent`

Deferred because rootless podman does not honour `--security-opt apparmor=...`,
so these container profiles are not actually applied in practice today. When
that changes (rootful podman, a different runtime, or upstream lifting that
restriction), decide between:

(a) Add a new `container` category to `roles/apparmor/app_categories.yml` and
    switch the include to `local_mixin_personal_dirs__for__container`. With no
    paths in `personal_dirs.yml` listing `container` in their `allow`, every
    rule becomes `audit deny`, matching today's behaviour but expressed in
    the new framework.
(b) Drop the include from `container_base` entirely, leaving container
    profiles unaware of personal dirs. Cleaner if containers should never
    even see those paths.

Either way, the deprecated mixin can only be removed after this is resolved.

## `local_pathbased_anydesk` does not include any personal_dirs abstraction

Unlike every other pathbased profile, `templates/anydesk/local_pathbased_anydesk.aa.j2`
does not include `local_mixin_deny_personal_dirs` (legacy) or any
`local_mixin_personal_dirs__for__<category>` (new). Per the convention now
documented in `roles/apparmor/CLAUDE.md` ("every pathbased profile must
`#include` exactly one"), anydesk should be brought into compliance, most
likely with `__for__others`. Defer until a deliberate review of what anydesk
actually needs - remote-desktop access patterns differ enough that the safest
default may not be the right one.
