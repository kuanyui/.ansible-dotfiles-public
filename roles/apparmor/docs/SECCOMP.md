# Hardened desktop launchers - SPEC (seccomp wrapper + `.desktop` override)

Status: PLAN, not implemented. Telegram is the first target; mpv / vlc / other profiled
apps follow. (Filename kept as SECCOMP.md; scope is now broader than seccomp - rename to
HARDENED_LAUNCHERS.md is an open decision below.)

## 1. Goal & threat model

AppArmor attaches to every profiled app by path (kernel-enforced, every launch) but mediates
only LSM hooks (file / cap / network-family / mount / ptrace / signal / userns / io_uring /
mqueue). It does **not** filter syscalls. This spec adds a seccomp layer to cover that blind
spot, applied on the GUI launch path, for profiled apps that do not already self-sandbox.

AppArmor-blind LPE (local privilege escalation) primitives we want gone - none used by these apps:

| Primitive | AppArmor? | Only blockable by |
|---|---|---|
| `userfaultfd` | no | seccomp, or `vm.unprivileged_userfaultfd=0` |
| `perf_event_open` | no | seccomp, or `kernel.perf_event_paranoid>=2` |
| `keyctl` / `add_key` / `request_key` | no (deny_keyrings blocks only file paths) | seccomp |
| `io_uring` setup | yes (`audit deny io_uring`) | seccomp = defense-in-depth |
| SysV shm/sem (`shmget`/`semget`) | no (mqueue deny = msg queues only) | seccomp |
| `bpf` | no | seccomp, or `kernel.unprivileged_bpf_disabled=1` |
| new mount API (`fsopen`/`move_mount`/`mount_setattr`/...) | partial (AppArmor mediates `mount`) | seccomp `@mount` = defense-in-depth |

## 2. Scope (calibration - do NOT blanket-apply)

| App class | Wrapper? | Reason |
|---|---|---|
| Browsers / Electron (firefox, chromium, msedge, vscode) | NO | self-apply seccomp-bpf to renderer processes; an outer filter can break their sandbox |
| Network-facing (telegram, anydesk) | YES | highest value |
| Media players (mpv, vlc) | YES | parse untrusted codecs / subtitles / containers = real kernel parser surface |
| Other local viewers (gwenview, okular, mcomix, stardict, mscore) | LATER / LOW | network already AppArmor-denied; only value is a kernel bug via malicious file parsing |

## 3. Mechanism

### A. Generic wrapper `~/.local/bin/seccomp-launch`

One file, app-agnostic. Signature: `seccomp-launch [VAR=value ...] <binary> [args...]` -
leading `VAR=value` tokens (env(1)-style) carry per-app env (e.g. Telegram's
`LIBGL_ALWAYS_SOFTWARE=1`) from the registered list (3C); the first non-assignment arg is the
target binary. Applies seccomp via a transient systemd `--user` **service** (NOT `--scope` -
see verified facts). The service does NOT see your session env (see 4); the wrapper rebuilds a
minimal env from a vetted allowlist with `env -i` (default-deny, like sudo's `env_reset`).

```bash
#!/bin/bash
# THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY (src: roles/apparmor/templates/.../seccomp-launch.j2)
set -euo pipefail

# Per-app env arrives as leading VAR=value tokens (env(1)-style); the .desktop writes e.g.
#   seccomp-launch LIBGL_ALWAYS_SOFTWARE=1 /usr/bin/Telegram %u
# Collect them; the first non-assignment arg is the target binary.
EXTRA_ENV=()
while [[ "${1:-}" == *=* && "${1%%=*}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; do
  EXTRA_ENV+=("$1"); shift
done
target="$1"; shift

# The transient --user service inherits the systemd --user MANAGER env block, NOT the caller
# env, and that block is shared + runtime-mutable: any same-user process can `systemctl --user
# set-environment LD_PRELOAD=...` and it lands in every later unit (see 4). So do NOT trust it:
# `env -i` wipes the inherited block and we re-add only a vetted allowlist (values read here, in
# the live caller session). Default-deny env, like sudo's env_reset; this also keeps session
# secrets (SSH_AUTH_SOCK, *_TOKEN) out of the confined app.
# Safe to extend with display-tuning vars if needed (GTK_THEME QT_SCALE_FACTOR GDK_SCALE ...);
# NEVER add an injection var (LD_*, QT_PLUGIN_PATH, GTK_PATH, GIO_MODULE_DIR, GST_PLUGIN_PATH,
# PERL5LIB, NODE_OPTIONS, ...) - that re-opens exactly the hole env -i closes.
ALLOW=()
for v in HOME PATH USER LOGNAME \
         XDG_RUNTIME_DIR XDG_DATA_DIRS XDG_CONFIG_DIRS \
         XDG_DATA_HOME XDG_CONFIG_HOME XDG_CACHE_HOME \
         WAYLAND_DISPLAY DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE \
         DBUS_SESSION_BUS_ADDRESS \
         LANG LANGUAGE LC_ALL LC_CTYPE LC_MESSAGES \
         GTK_IM_MODULE QT_IM_MODULE XMODIFIERS QT_QPA_PLATFORM; do
  [ -n "${!v:-}" ] && ALLOW+=("$v=${!v}")
done

CMD=(systemd-run --user --pipe --wait --collect
  -p SystemCallArchitectures=native          # close 32-bit/x32 ABI seccomp bypass
  -p SystemCallErrorNumber=EPERM             # denied syscall -> EPERM, not SIGSYS kill (fail-soft)
  -p 'SystemCallFilter=~userfaultfd perf_event_open keyctl add_key request_key bpf @io_uring @mount @clock @obsolete @cpu-emulation @raw-io @swap @reboot @module @debug'
  /usr/bin/env -i "${ALLOW[@]}" "${EXTRA_ENV[@]}"   # default-deny env: only allowlist + per-app env survive
  "$target")

printf 'seccomp-launch: %q ' "${CMD[@]}" "$@"; echo   # transparency: print the FULL command (incl. args)
exec "${CMD[@]}" "$@"
```

### B. `.desktop` override by DERIVE-REWRITE (not hand-written)

`.desktop` entries do NOT merge - a same-ID file in a higher-precedence dir fully REPLACES the
lower one (no inheritance in the spec). So a hand-written override would have to replicate the
distro's `Icon` / `MimeType` / `Actions`, and drift on distro updates. Instead, DERIVE it:

1. Read the distro entry `/usr/share/applications/<id>.desktop`.
2. Rewrite every `Exec=` line (including each `[Desktop Action ...]` block - the right-click
   jump-list sub-launchers, each has its own `Exec=`) to route through the wrapper:
   `Exec=<orig>` -> `Exec=<seccomp-launch> <extra_env as VAR=value ...> <orig-tail>`. Per-app
   env is emitted as leading `VAR=value` tokens the wrapper folds into `env -i` (3A) - NOT a
   session-level `env VAR=x` prefix: that sets it in the caller, and the transient service does
   not inherit the caller env, so `env -i` would never see it (see 4).
3. Rewrite `Name=` (and every localized `Name[xx]=`) to append ` (hardened)` - this is the
   VISIBLE marker that you launched the wrapped entry, and the distro's plain entry is hidden
   by the same-ID override, so the menu shows exactly one `X (hardened)`.
4. **Neutralize `DBusActivatable`** - replace `DBusActivatable=true` with `DBusActivatable=false`
   (if the key is absent, default is already `false` - nothing to do). REQUIRED: per the Desktop
   Entry Spec a `true` value makes launchers "ignore the `Exec` key and send a D-Bus message"
   (4), so a spec-compliant launcher (GNOME Shell, KDE) would skip our rewritten `Exec=` and
   start the app UNWRAPPED. AppArmor still attaches (path-based, every execve) but seccomp would
   be silently absent. No downside to forcing `false`: the app's own single-instance logic still
   forwards a second launch to the running instance.
5. Keep `TryExec=` as-is (points at the real binary; correctly gates visibility).
6. Write to `~/.local/share/applications/<id>.desktop` (same ID, higher precedence => overrides).

> **Second D-Bus surface** (separate from the key above): a `DBusActivatable` app usually also
> ships a bus *service activation file* `/usr/share/dbus-1/services/<id>.service` (keys
> `Name`/`Exec`/`SystemdService`). A client that activates it by BUS NAME (not via the
> `.desktop`) hits that file directly => unwrapped. `DBusActivatable=false` does NOT cover this.
> Per dbus-daemon(1) `$XDG_DATA_HOME/dbus-1/services` (`~/.local/share`) precedes `/usr/share`,
> so it CAN be shadowed the same way (same-`Name` file, `Exec=seccomp-launch ...`, omit
> `SystemdService=`). DECISION for the first batch (telegram/mpv/vlc - none use GApplication
> D-Bus activation, so none ship such a file): accept it as an escape hatch (AppArmor on,
> seccomp off), like the bare-name path in 6. Add the service-file shadow only if a target app
> actually ships one.

ansible-core feasible: `slurp` -> `regex_replace('(?m)^Exec=', ...)` + `regex_replace('(?m)^Name(\[[^]]*\])?=', ... ' (hardened)')` + `regex_replace('(?m)^DBusActivatable=true\b', 'DBusActivatable=false')` -> `copy`.

Re-derived on every apply => tracks distro `Icon`/`MimeType`/`Actions` updates automatically.

Edge handling - WARN, do NOT fail the run (user decision):
- Distro source entry missing (app not installed, or distro renamed its desktop file ID):
  emit a VISIBLE warning and skip that app. Do not abort the playbook. (Consistent with
  "fail loudly" = visible, not necessarily fatal.)
- Net effect of a renamed distro ID: our override silently stops shadowing and a fresh
  un-wrapped distro entry can reappear - the warning is the tripwire for that.

### C. Idempotence - mirror the existing profile-registration pattern

Filenames are now distro IDs (not `ansible_*`), so cleanup CANNOT key on the `ansible_*`
prefix. Use the same pattern the role already uses for profiles:

- Register every managed entry in a list in `defaults/main.yml` (cf. `apparmor_template_profile_names`):
  `{ id: org.telegram.desktop.desktop, binary: /usr/bin/Telegram, extra_env: [LIBGL_ALWAYS_SOFTWARE=1] }`.
- Deploy loop reads the list; a deprecated-names list drives removals (cf. the current
  hardcoded `state: absent` blocks - e.g. retire `ansible_telegram.desktop`).
- **Marker line (DECIDED): reuse the existing repo convention, do not invent a new one.** Zero
  migration; already documented in `roles/apparmor/CLAUDE.md`.
  - `.desktop` first line (injected on derive; the distro source has none):
    `# THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY`
  - `~/.local/bin/seccomp-launch`: the shell-script BLOCK form (`# ===` lines around
    `THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY`), per the role CLAUDE.md.
  - Greppable load-bearing token: `THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY`.
- Its ONLY machine job is a pre-clobber SAFETY ASSERT: before overwriting/removing the one
  target path `~/.local/share/applications/<id>.desktop`, if it already exists and does NOT
  contain the token, it is a user-authored file -> WARN and refuse, never clobber. A generic
  token suffices (we only need "ours vs the user's", and we grep only that one path). It is NOT
  a discovery key: a repo-wide "grep marker -> delete" sweep would nuke any user file containing
  the string. Discovery stays the explicit registered set (the list above).
- Derived `.desktop` files add a 2nd human comment line:
  `# Derived from /usr/share/applications/<id>.desktop by roles/apparmor - regenerated each apply`.

## 4. Verified facts (checked upstream - do NOT re-derive from memory)

- **`systemd-run --scope` cannot apply seccomp.** `SystemCallFilter` is service-unit only; a
  scope is forked by systemd-run, bypassing the manager exec path. => use a transient service.
- **A transient `--user` service runs with the systemd `--user` MANAGER env block, not the
  caller's env** (the manager is its parent). That block is shared and runtime-mutable: any
  same-user process can `systemctl --user set-environment VAR=value`, and per systemctl(1) the
  two blocks are "combined ... and passed to" every later-spawned unit. So a compromised
  same-user process could inject `LD_PRELOAD`/`LD_AUDIT` into the next hardened launch. The
  wrapper therefore does NOT trust it: `/usr/bin/env -i` wipes the inherited block and re-adds
  only a vetted allowlist (values read from the live caller session), `env(1)`-style.
  Allowlist (default-deny), not a denylist of "dangerous" vars: the injection-var set (ld.so
  family + every toolkit's `*_PLUGIN_PATH`/`*_MODULE*` + interpreter vars) is unbounded and
  grows per release, so one missed entry = full bypass. Same rationale as sudo's `env_reset`.
  (Note: this is the OPPOSITE choice from the seccomp syscall filter in 5, which is a denylist -
  there the *needed* set is huge and the *dangerous* set small, so the asymmetry flips.)
- **`--pipe --wait`** => synchronous, stdio passes through (behaves like a normal command from
  a terminal too).
- **Repeated `-p SystemCallFilter=` merge-vs-override is undocumented** => use a single
  denylist assignment (avoids the question; also robust to quoting).
- **`.desktop` ID** = file path relative to the `$XDG_DATA_DIRS` component, minus the
  `applications/` prefix, with `/` -> `-`. For a file directly under `applications/` (no
  subdir) the ID equals the filename. Same ID across dirs: the higher-precedence dir wins, and
  `~/.local/share/applications` (`$XDG_DATA_HOME`) is searched before `/usr/share/applications`.
  Source: https://specifications.freedesktop.org/desktop-entry/latest/file-naming.html
- **`DBusActivatable=true` makes launchers ignore `Exec`.** Desktop Entry Spec: "If the value is
  `true` then implementations should ignore the `Exec` key and send a D-Bus message to launch the
  application." Hence the derive forces it `false` (3B), else the `Exec=` rewrite - and the
  seccomp wrapper with it - is bypassed. A bus-NAME activation instead reads a `.service` file
  from the `$XDG_DATA_HOME`-first search path (dbus-daemon(1)) - a separate surface (note in 3B).
  Source: https://specifications.freedesktop.org/desktop-entry/latest/recognized-keys.html

## 5. seccomp filter: denylist (deliberate)

- Denylist (`~...`), not an `@system-service` allowlist: the workflow is enforce-only with no
  `SystemCallLog=` validation pass, so an allowlist risks EPERM-breaking the app. The denylist
  kills exactly the AppArmor-blind primitives (section 1); these apps never use them => near-zero
  breakage. (Opposite of the env handling in 3A, which IS an allowlist: there the *needed* set is
  small and the *dangerous* set unbounded, so allowlist wins; here the *needed* set is huge and
  the *dangerous* set small, so denylist wins.)
- The set (group contents verified against systemd `seccomp-util.c`):
  `~userfaultfd perf_event_open keyctl add_key request_key bpf @io_uring @mount @clock @obsolete
  @cpu-emulation @raw-io @swap @reboot @module @debug`. Recent-LPE-driven members: `@io_uring` /
  `userfaultfd` / `perf_event_open` (2022-23 kernel-exploit favourites), `bpf` (eBPF verifier
  LPEs; member of `@privileged`), `@mount` (new mount API - `fsopen`/`move_mount`/`mount_setattr`).
  `@debug` already covers `perf_event_open`/`ptrace`/`pidfd_getfd`, `@reboot` covers `kexec_load`
  (kept the explicit names for readability). Add `process_vm_readv`/`process_vm_writev` only if a
  target app proves not to need them (some crash handlers do) - they are ptrace-mediated by
  AppArmor anyway.
- Scope of value: this PATCHES AppArmor's syscall blind spot. It is NOT a full sandbox -
  `setsockopt`/`futex`/`ioctl` etc. stay open (an allowlist would not block those either).
- Upgrade path (later, stronger): base on `@system-service`, run once with `-p SystemCallLog=`
  (mirrors aa-complain), collect from `journalctl --user`, tighten, then enforce.

## 6. Terminal launches & verification

- The `.desktop` override only covers GUI / MIME-handler launches. A terminal launch by bare
  name is a separate path: a `~/.local/bin/<name>` shadow catches it (interactive shell PATH
  has `~/.local/bin`; the GUI/session PATH does not - so the GUI side MUST use the override,
  not PATH). A deliberate `/usr/bin/X` stays an intended bare escape hatch (AppArmor still on).
- Verify protection anytime, regardless of launch path:
  `grep Seccomp /proc/$(pgrep -x Telegram)/status` -> `2` = filtered, `0` = none.

## 7. Optional system-wide sysctl hardening (not per-app)

`vm.unprivileged_userfaultfd=0`, `kernel.perf_event_paranoid>=2`,
`kernel.unprivileged_bpf_disabled=1`, `kernel.yama.ptrace_scope>=1`.

## 8. Open decisions

- [ ] Wrapper name (`seccomp-launch`?).
- [x] Per-app `extra_env` representation: DECIDED - emitted as leading `VAR=value` tokens on the
      `Exec=` line, folded into `env -i` by the wrapper (3A/3B). The list stays per-app, never
      global (Telegram needs `LIBGL_ALWAYS_SOFTWARE=1`; media players must NOT force software GL).
- [ ] Append ` (hardened)` to localized `Name[xx]=` too, or only the main `Name=`?
- [ ] Which apps in the first batch (telegram + mpv + vlc?), which deferred.
- [ ] Allowlist upgrade vs keep denylist.
- [ ] Rename this doc to HARDENED_LAUNCHERS.md?
- [ ] Implement: wrapper template + derive-rewrite task + `defaults` registered list +
      retire old `ansible_telegram.desktop`; run `make apparmor-sandbox`.

## Sources

- https://specifications.freedesktop.org/desktop-entry/latest/file-naming.html
- https://specifications.freedesktop.org/desktop-entry/latest/recognized-keys.html (DBusActivatable)
- https://wiki.archlinux.org/title/Systemd/Sandboxing
- https://man.archlinux.org/man/systemd-run.1.en
- https://man.archlinux.org/man/systemctl.1.en (set-environment: shared mutable manager env)
- https://man.archlinux.org/man/dbus-daemon.1.en (D-Bus service activation file search/precedence)
- https://wiki.archlinux.org/title/Systemd/User
