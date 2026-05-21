# TODO

## `python3-jsonschema` install: handled by the role itself

`scripts/gen_personal_dirs_aa_mixins.py` validates
`roles/apparmor/local_vars/personal_dirs.yml` against a JSON Schema at playbook
run time using the `jsonschema` Python package.

Handled by:

- `roles/apparmor/tasks/common.yml`: an `ansible.builtin.package` task installs
  `python3-jsonschema` (same package name on Debian / openSUSE / Fedora) before
  the builder is invoked. `ansible_pkg_mgr` dispatches to the right backend.
- `scripts/sandbox/configs/apparmor.py`: `extra_packages_apt` also lists
  `python3-jsonschema` so the sandbox image has it from build time, before
  the playbook even runs.
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

## Extract `local_mixin_gpu_probe` abstraction (deferred)

Two profiles currently inline the same "allow userspace GPU/render API metadata
probing without granting hardware access" pattern:

- `templates/mpv/local_base_mpv.aa.j2` - `/dev/dri/`, `/usr/share/vulkan/{icd.d,implicit_layer.d}/`, `/usr/share/glvnd/egl_vendor.d/`
- `templates/telegram/local_pathbased_telegram.aa.j2` - `/usr/share/glvnd/egl_vendor.d/` (Qt EGL probe)

`files/profiles/local_mixin_gpu.aa` also contains the same 4 paths.

When a third caller (some Qt/GTK app intentionally denied GPU hardware but still
probing render APIs at startup) hits the same audit-log spam, extract a new
abstraction:

- `files/profiles/local_mixin_gpu_probe.aa` - the 4 read-only paths above.
- Refactor `local_mixin_gpu` to `#include` the new probe mixin, so the layering
  becomes `gpu_probe` (metadata only) `subset of` `gpu` (metadata + hardware nodes).
- Replace the inline rules in mpv base and telegram pathbased with the include.

Why deferred (2026-05-21): only 2 callsites, and their path sets are not
identical (telegram only needs glvnd; mpv also needs vulkan + `/dev/dri/`).
Premature extraction would either over-grant inert config reads to telegram or
require a more granular split. The break-even point is the 3rd caller, when
the minimal shared set and naming will be more obvious.

Security invariant to preserve when extracting: the new mixin must NEVER include
`/dev/dri/renderD*` or `/dev/nvidiactl`. Those device nodes are the actual GPU
boundary and must stay exclusively in `local_mixin_gpu`.
