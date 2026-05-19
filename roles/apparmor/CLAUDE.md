# Project Conventions

## Comments
All comments anywhere in the project must be written in English. This includes tasks, templates,
inventory files, and any other configuration files. No Chinese or other languages.

Never remove existing comments when editing or refactoring files. If code is moved to a different
file, its comments must move with it.

Always use the standard ASCII hyphen (-) as a dash. Never use em dashes (—) or en dashes (–).

Section headers in task files and templates must use this format:
```
# =============================================
# Title
# =============================================
```

## Ansible-managed files deployed to user home directories

Every file deployed to `~/.local/bin/` or `~/.local/share/applications/` must include a prominent
"MANAGED BY ANSIBLE" warning so the user knows not to edit it manually and knows where the source
lives.

Shell scripts in `~/.local/bin/`: place the warning block immediately after the shebang line:
```
#!/bin/bash
# =============================================================================
# MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY
# =============================================================================
```

`.desktop` files in `~/.local/share/applications/`: place a `#` comment line at the very top of
the file, before the `[Desktop Entry]` section:
```
# MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY
```

## AppArmor pathbased profile task files

Every pathbased profile task file must include logic to back up and remove any conflicting
system-provided profile from `/etc/apparmor.d/` into
`_backup_of_default_profiles_from_package_manager/`. This applies to every new pathbased profile
added in future. Use the chromium.yml task as the reference pattern: stat each candidate system
profile name, copy if it exists, remove from apparmor.d, flush handlers, then run
`apparmor_parser -R` against the backup to unload it from the kernel.

## Role Organization
All AppArmor hardening and security enforcement (AppArmor profiles, bwrap wrappers, seccomp
filters, and related configuration) belongs in `roles/apparmor/`, regardless of whether the
profiles are static or dynamically generated. Static profiles go in
`roles/apparmor/files/profiles/`. Templates go in `roles/apparmor/templates/`. Per-application
task files go in `roles/apparmor/tasks/` and are imported from `roles/apparmor/tasks/main.yml`.

## Makefile target naming
Target names must clearly describe behavior, not just the subject. A target that blocks and
follows output in real time must include `-watch`. A target that reads a static snapshot must
include `-snapshot` or `-recent`. Never use a bare noun like `aa-log` when the behavior is
ambiguous.

## become
Never set `become: true` at the play level when a role mixes privileged and unprivileged tasks.
Set `become: true` per-task instead, and default the play to `become: false`.

## AppArmor profile naming

All profiles deployed to `/etc/apparmor.d/` must follow these naming rules - both the filename
and the profile name inside the file must match:

- All local profiles: prefix `local_` (e.g., `local_firefox`)
- Attachment-less profiles (no executable attachment, must be invoked manually via `aa-exec` or
  similar): prefix `local_attachmentless_` (e.g., `local_attachmentless_bwrap_sandbox`)

File extensions:
- Static profiles: `.aa` suffix (e.g., `local_attachmentless_glycin.aa`)
- Jinja2 templates that generate profiles: `.aa.j2` suffix (e.g., `local_attachmentless_firefox.aa.j2`)

## AppArmor profile #include layout

All `#include` directives must appear at the top of the profile body, before any rules.
Never place `#include` lines at the bottom or interspersed among rules.

Do not insert blank lines between consecutive `#include` lines.

## AppArmor file permission modes

Valid mode characters for file rules in AppArmor policy syntax:

| Mode | Covers |
|------|--------|
| `r`  | read |
| `w`  | write, append, truncate, create, **unlink (delete)** |
| `a`  | append only (no truncate) |
| `x`  | execute (combined with qualifier: `ix`, `px`, `cx`, `ux`) |
| `m`  | memory-map executable (`mmap PROT_EXEC`) |
| `k`  | file locking (`flock`) |
| `l`  | hard link creation |

**`d` is NOT a valid policy mode.** It appears in audit logs (`requested_mask=d`, `denied_mask=d`)
as the kernel-internal representation of unlink. To allow unlink, write `w` in the policy.

Audit log masks do not map 1:1 to policy syntax. Never copy a mask letter from an audit log
directly into a policy rule without verifying it is a valid policy mode from the table above.

## Security concept distinctions

These three are distinct and must not be conflated:

- **Namespace isolation**: Linux kernel mechanism (bwrap). Limits what a process can *see*.
  Not MAC. A process inside a user namespace is still subject to AppArmor policy on the host.
- **MAC / AppArmor**: LSM kernel hook. Enforces policy on file access, capabilities, IPC.
  `flags=(attach_disconnected)` is an AppArmor flag, not a namespace concept.
- **Sandbox**: a *goal*, not a primitive. bwrap + AppArmor together form a sandbox.

Never call an AppArmor profile a "sandbox profile". Never suggest `Ux` to fix disconnected-path
denials - that removes MAC. The correct fix is `flags=(attach_disconnected)`.
