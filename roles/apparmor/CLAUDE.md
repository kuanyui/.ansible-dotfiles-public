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

## Ansible-managed files: the THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY marker (ALL file types, ALL destinations)

Every file this role writes OUTSIDE the repo - ANY type, ANY destination a human might find and
hand-edit (`~/.local/bin/`, `~/.local/share/applications/`, `/etc/apparmor.d/`, XDG config dirs,
...) - must carry a prominent `THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY` marker at its top, so the
reader knows not to hand-edit it and where the source lives. This is UNIVERSAL - not only bash
scripts, not only `.desktop` files.

Placement: if the format has a mandatory first line (shebang `#!`, `<?xml?>`, ...) the marker goes
IMMEDIATELY AFTER it; otherwise the marker IS the first line. Use the file type's native comment leader:

| File type | Marker line |
|-----------|-------------|
| shell, YAML, `.desktop`, `.aa` (AppArmor), `.conf`/`.ini`, Python, Dockerfile | `# THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY` |
| C-like / JSONC | `// THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY` |
| XML / HTML | `<!-- THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY -->` |

Formats with NO comment syntax (strict JSON, `key=value` configs that reject `#`, binary) cannot
carry an inline marker - do NOT inject an invalid line; note the management elsewhere or accept the
exception explicitly.

The token `THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY` is a load-bearing machine
sentinel - one whitespace-free, all-caps string chosen so a `grep -F` detects it with zero
case/whitespace/wrap ambiguity and effectively never collides with human prose. Two uses:
- A deployed file CONTAINS the token => it is OURS (regenerable) - safe to delete / clobber /
  regenerate on sight.
- A target path EXISTS but the token is ABSENT => user-authored - NEVER clobber (e.g. the
  pre-clobber assert in `tasks/seccomp.yml`).
Keep it verbatim everywhere - it is the contract.

Concrete forms:

Shell scripts in `~/.local/bin/`: place the warning block immediately after the shebang line:
```
#!/bin/bash
# =============================================================================
# THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY
# =============================================================================
```

`.desktop` files in `~/.local/share/applications/`: place a `#` comment line at the very top of
the file, before the `[Desktop Entry]` section:
```
# THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY
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

A new static profile/mixin under `files/profiles/` is NOT deployed until it is registered in
`apparmor_static_profiles` / `apparmor_static_abstractions` in `defaults/main.yml` (the deploy
loop in `tasks/static.yml` reads those lists, not a glob). Creating the file and adding a
profile's `#include` alone makes `apparmor_parser` fail on the missing include. The same lists
also feed the idempotent `local_*` cleanup allowlist, so registering protects the file from
removal as an orphan.

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

## Per-category customized_extra_dirs abstractions

Every pathbased profile must `#include` exactly one of the per-category
abstractions generated at playbook run time:

```
#include <abstractions/local_mixin_customized_extra_dirs__for__<category>>
```

where `<category>` is one of the names listed in
`roles/apparmor/app_categories.yml`. Apps that do not fit any specific
category use `others`.

Source of truth:

- `roles/apparmor/app_categories.yml` - the category list (single source).
- `roles/apparmor/local_vars/customized_extra_dirs.yml` - per-path access policy,
  gitignored. Scaffolded by `roles/apparmor/scripts/gen_customized_extra_dirs_definitions_yaml.py` and
  then hand-edited.
- `roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py` - validates the YAML against
  a JSON Schema (with the category enum injected from `app_categories.yml` at
  run time) and emits one abstraction per category.

Hard runtime dep: the builder requires the distro-provided
`python3-jsonschema` package. See `roles/apparmor/TODO.md`.

The companion JSON Schema is written next to the YAML on every scaffold and
every playbook run (`roles/apparmor/local_vars/customized_extra_dirs.schema.json`,
gitignored). The scaffolded YAML's first line is a `yaml-language-server`
directive pointing at it, so editors with the Red Hat YAML extension (or
coc-yaml / lsp-mode) validate inline and autocomplete categories.

The `local_mixin_customized_extra_dirs__DENY_ALL` abstraction denies every listed
directory regardless of its `allow` list (generated from the same
`customized_extra_dirs.yml` source). Include it in profiles that must never touch any
customized directory - e.g. container base profiles. It replaced the old,
separately-sourced all-or-nothing deny mixin.

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

## audit deny vs plain deny

Two deny forms, chosen by one test: **is a denied attempt a SIGNAL or NOISE?** (Not "should it
access this?" - least-privilege denies both regardless.)

- `audit deny` = security tripwire. Sensitive target or never-legitimate access; a denied hit is
  worth seeing in the log. E.g. `local_mixin_deny_keyrings`, `local_mixin_deny_persistent_attack`.
- plain `deny` = silence benign noise. Routine access some library does on every launch (GPU
  device/ICD probes, NSS `getpwuid`, machine-id, `find_library` ldconfig/compiler probes); a
  denied hit is noise. Silencing keeps the real `audit deny` tripwires visible instead of buried.

## Least-privilege scoping (strictly audit-driven)

Profile and mixin rules must be **strictly audit-driven**. When extending a profile or mixin
in response to a denial, the default posture is the narrowest rule that fixes the audited
denial. NOT one mode wider, NOT one path level deeper, NOT one extra parent dir.

- **Only audited paths.** If audit shows `/sys/bus/` and `/sys/bus/usb/devices/`, the rule is
  two specific lines, NOT `/sys/bus/{,**} r,`. If a deeper path appears in a later audit,
  expand then. Same for `{,**}` glob suffixes - only add the suffix when sub-path access is
  actually audited.
- **Only audited modes.** Audit shows `r` -> rule is `r`, not `rwk`. Audit shows `chmod`
  (`w` mask in policy) -> rule is `w`, not `rw`. Add `k` (flock), `l` (hard link), or `m`
  (mmap exec) only when the corresponding operation appears in audit, never preemptively
  "because it's a state file / library / cache".
- **No speculative parent dirs.** If audit shows chmod on `~/.cache/foo/normal/`, do not
  also grant `~/.cache/foo/`. The parent is added only if a future audit shows an operation
  on the parent itself.
- **Mixin scope is multiplied.** A rule in a mixin grants that access to every profile that
  includes the mixin. Before adding to a mixin, confirm the path is needed by 3+ distinct
  callers (the "3rd-caller rule" - see TODO.md). Until then, inline into the single profile
  that needs it. A single audit hit is NEVER enough evidence to promote an app-specific path to
  a mixin. (Exceptions - library-determined paths and shared `deny` rules - in **Mixin
  promotion** below.)
- **`owner` keyword by default** on any `~/` or `/proc/<pid>/` rule. For self-introspection,
  prefer `@{PROC}/@{pid}/...` (literally own pid) over `owner /proc/[0-9]*/...` (any
  same-user pid) - the threat model assumes the confined app may be compromised, and
  cross-process info disclosure between same-user pids is still disclosure.
- **No "since we're already adding".** Adjacent rules that look related but are not audited
  do not get a free ride.

The cost of being too narrow is one extra audit iteration. The cost of being too broad is
attack surface that takes a security review to find again.

## Mixin promotion (refines the 3rd-caller rule)

The "3rd-caller rule" above is the default for **app-specific** paths. Three refinements:

- **Library/framework-determined path** - fixed by a library, not chosen by the app (glycin's
  `gdk-pixbuf-glycin-tmp.*` temp prefix, `/etc/machine-id`, `recently-used.xbel`). Structural
  sharing is already proven, so a mixin is justified on the FIRST caller; no need to wait for 3.
- **deny-mixin vs allow-mixin asymmetry** - a shared `deny` only ever REMOVES access, so it is
  safe to create early. A shared `allow` GRANTS surface to every includer; keep it inline until
  a 2nd+ caller genuinely needs it.
- **The mixin test is "do all includers want the same policy?"** - NOT "is it a standard path?".
  `recently-used.xbel` is an XDG standard, but browsers want it denied while local viewers want it
  allowed, so it must NOT live in `local_mixin_gtk`/`local_mixin_xdg` (both included by browsers).
  Split-policy paths stay inline, or get a dedicated opt-in mixin.
- **Privilege-boundary transitions stay per-profile** even when library-determined - e.g.
  `/usr/bin/bwrap Px -> local_attachmentless_glycin,` plus its `signal (send) set=(kill)`. Each
  profile's right to spawn a more-privileged peer must be visible in that profile, not in a mixin.
- **Existing domain mixin overrides the 3rd-caller wait.** The 3rd-caller rule above is about
  whether to CREATE a new mixin. When an existing `local_mixin_<subsystem>.aa` already owns the
  audited path's semantic domain (e.g. an audit hit on `gdk-pixbuf-glycin-tmp.??????` and
  `local_mixin_glycin.aa` already exists), the new rule goes IN that mixin from day 1 - do NOT
  inline first and "promote later". Practical test before placing a rule: `ls roles/apparmor/files/profiles/local_mixin_*.aa`
  and check if any subsystem keyword in the audited path (`glycin`, `kio`, `xdg`, `pipewire`,
  `vulkan`, `mesa`, ...) matches an existing mixin name. If yes - rule goes there. Rationale: inlining
  when a domain mixin sits right there means the next profile hitting the same denial independently
  re-inlines it, fragmenting maintenance across N profiles instead of one mixin.

## Threat-model calibration

Calibrate deny/allow to the specific app, not a blanket "deny anything sensitive-ish". Before
denying a feature-enabling path, ask: does THIS app have network egress? Does it process untrusted
input? Is the data sensitive (contents/secrets) or low-value metadata (paths/timestamps)?

A no-network local viewer earns more allow-latitude than a browser. Do not copy another profile's
deny without checking its threat model applies: firefox denies `recently-used.xbel` because it is
network-facing and runs untrusted content; mcomix allows it (its profile denies all network), so a
compromised viewer cannot exfiltrate the recents, and the user keeps the feature.

## Sandbox must exercise every feature (plant fixtures, assert output)

`make sandbox-apparmor` is the verification gate. If a feature only runs when an external
precondition holds - e.g. `tasks/seccomp.yml`'s derive needs an installed app's
`/usr/share/applications/<id>.desktop` - the sandbox SILENTLY SKIPS it, leaving the riskiest
logic untested. So for any such feature: (1) plant the fixture in
`scripts/sandbox/configs/apparmor.py` (`post_setup_commands` writes a stub source, or
`extra_files`), AND (2) assert the produced output in `post_check`. Never ship sandbox-skippable
logic on "the real machine will test it" - that is exactly how the seccomp derive shipped
untested once (the stub `org.telegram.desktop.desktop` + `_post_check_seccomp_derive` exist to
prevent a repeat).
