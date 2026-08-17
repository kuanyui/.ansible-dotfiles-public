# TODO

## `local_pathbased_dbeaver` (portable tarball) - complain round 1 applied 2026-08-14

New profile for the official DBeaver CE binary tarball, run in place (no install). Name-based
attachment `/**/dbeaver` like anydesk. Whole unpack tree allowed (`owner /**/dbeaver/** rwkm`);
workspace `~/.local/share/DBeaverData/`; network via `local_mixin_network_app`; browser data /
SSH+GPG keys / clipboard stores / ALL customized_extra_dirs (DENY_ALL variant) hard-denied.

- [x] Round 1: first-launch denials (2026-08-14) folded into the profile.

  | Denial | Verdict |
  |--------|---------|
  | `~/.swt/` mkdir | allow `rw` + `**  rwm` - SWT native extraction, denying it pushes the same `.so` into `$HOME` instead |
  | `/sys/kernel/mm/hugepages/`, `.../transparent_hugepage/shmem_enabled` | allow `r` - HotSpot large-page probe |
  | `/proc/sys/vm/mmap_min_addr` | allow `r` |
  | `/proc/<pid>/net/if_inet6` | allow `r` WITHOUT `owner` - proc net files are root-owned, so the existing `owner @{PROC}/@{pid}/**` cannot match |
  | `/proc/<pid>/coredump_filter` | allow `owner ... w` - self-scoped |
  | glycin: `conf.d/**` reads, then `exec /usr/bin/bwrap` from `gly-hdl-loader` | `#include <abstractions/local_mixin_glycin>` + the caller-contract pair `bwrap Px -> local_attachmentless_glycin` and `signal (send) set=(kill)`, i.e. the same full stack as mcomix / stardict / firefox. Two wasted rounds got here: first a narrower inline dir rule (next launch denied every `*.conf`), then the mixin without the `Px` (next launch denied the bwrap exec, ~2 tries per image). DBeaver DOES decode through glycin - do not assume a Java/SWT app bypasses it |
  | AT-SPI bus `/run/user/*/at-spi/bus_1` | plain `deny` - cross-app UI read / input injection, not for a network-egress DB client |
  | `systemd/journal/socket` sendmsg (disconnected) | plain `deny` both forms + `flags=(attach_disconnected)`, mscore3 pattern |

- [ ] Round 2 after the next launch: confirm `~/.swt/**` is enough (round 1 saw only the denied
  `mkdir`, the subtree grant is inferred from SWT's `Library.loadLibrary`), and watch for the
  still-unseen blind-authoring candidates: `~/.java/` (Java Preferences API), `/usr/bin/xdg-open`
  (OAuth login flows open a browser), GTK portal paths. Then take it out of complain mode.

## `aaa-logs` recent-denials viewer - done 2026-07-02

New `/usr/local/bin/aaa-logs` (`files/aaa-logs`, deployed by `tasks/aaa_helpers.yml`). Standalone
twin of `make aa-log-recent LOG_SINCE_SECS=N`: `aaa-logs [SECONDS]` (default 60) prints AppArmor
denials from the last N seconds - `ausearch -m AVC` when auditd runs, else `journalctl --dmesg`,
both filtered through `grep --ignore-case apparmor`. Read-only inspector, so it lives in `bin`
(on a normal user's PATH; internal `sudo` for the privileged read, printed first). Sandbox:
`_post_check_aaa_logs`. The deploy task `rpmnew_helper.yml` was generalized to `aaa_helpers.yml`
(now deploys both aaa-rpmnew + aaa-logs).

## `aaa-rpmnew` post-update AppArmor reconciler - done 2026-07-02

New `/usr/local/sbin/aaa-rpmnew` (deployed by `tasks/rpmnew_helper.yml` from
`templates/aaa-rpmnew.py.j2`). After a distro update it ADOPTs the vendor `.rpmnew` for profiles
we do not manage, and re-NEUTRALIZEs distro profiles a `local_*` profile shadows, then reloads
AppArmor once (`sudo aaa-rpmnew`; `-y` / `--dry-run` / `--diff`; auto-sudo re-exec; prints every
privileged command before running it). Named `aaa-` (three a's) to sort clear of the built-in
`aa-*` tools and not be mistaken for one.

Single source of truth: new var `apparmor_shadowed_system_profiles` (`defaults/main.yml`). It
drives BOTH the per-app neutralize loops in
`tasks/{chromium,anydesk,gwenview,mcomix,mscore,mscore3,mpv}.yml` (refactored from literal
`loop:` name lists to read `apparmor_shadowed_system_profiles['<app>']`) AND the helper (the
flattened set is baked into the deployed script). Add a distro profile name to that var when a new
`local_*` profile shadows a packaged one - both consumers pick it up.

Sandbox: `_post_check_aaa_rpmnew` in `scripts/sandbox/configs/apparmor.py` plants a normal
`.rpmnew` + a resurrected shadowed profile and asserts ADOPT / NEUTRALIZE. Background + manual
runbook: `docs/RPMNEW_STALE_DISTRO_PROFILES.md`.

## VS Code Remote-SSH vs `~/.ssh` lockdown - PENDING DECISION 2026-07-01

Current design blocks VS Code Remote-SSH: `local_mixin_deny_keyrings` denies `~/.ssh/{,**}`, and
ssh inherits the vscode profile via `/usr/bin/{,*} rix`, so ssh cannot read `~/.ssh/config` /
`known_hosts` / private keys. Deliberate security tradeoff (protect keys from a compromised editor)
vs Remote-SSH's need to read keys. Chosen direction: give ssh its own child profile; real sealing
of the key needs ssh-agent + refusing the key-file grant. Full analysis, the "ssh is not a sealed
box" caveat (`ProxyCommand` etc.), and residual risks are in
`roles/apparmor/docs/PENDING_DECISION_vscode_remote_ssh.md`.

- [ ] Decide: agent-only (no `~/.ssh/id_*` file grant) vs keep key-file fallback
- [ ] Decide: ssh child-profile subprocess handling - `ix` inherit vs `px` narrow (affects `ProxyJump`)
- [ ] Then implement the child profile + `make sandbox-apparmor` (syntax only; real Remote-SSH needs on-host test)

## Telegram: bwrap wrapper dropped - 2026-06-21

Removed the bwrap launcher (`~/.local/bin/Telegram` wrapper + `ansible_bwrap_telegram.desktop`).
Telegram now runs under the path-based profile alone, launched directly via
`ansible_telegram.desktop` (`Exec=/usr/bin/env ... /usr/bin/Telegram`). Profile attachment is
unchanged - the `profile ... /usr/bin/Telegram` rule attaches at execve regardless of launcher.

The profile body still carries bwrap-era rules that were only safe under the namespace; they
need a complain-mode re-tightening pass on a real machine (cannot audit headless):

- [ ] `owner /run/user/*/* rwk` - under bwrap this hit only a throwaway `--tmpfs /run/user/<uid>`;
  with no bwrap it now grants r/w to the REAL runtime dir (pipewire / keyring / other apps'
  sockets). Complain-pass to capture which `/run/user` names Telegram's webview actually needs,
  then replace with narrow rules.
- [ ] `flags=(attach_disconnected)` - was needed for bwrap's disconnected /proc + /dev. Likely
  removable now; test (may still be needed for the journal-socket disconnected-path reporting).
- [ ] Stale comments referencing "bind-mounted by launcher" / "bwrap mounts --tmpfs /" and the
  `~/.config/` + `~/.cache/` mkdir rules (only existed because bwrap used `--tmpfs /`). Clean up
  in the same pass.

Procedure: `aa-complain local_pathbased_telegram`, exercise Telegram, `make aa-log-recent` /
`make aa-notify-snapshot`, tighten, `aa-enforce`.

## `personal_dirs` -> `customized_extra_dirs` rename - done 2026-06-17

Renamed the whole concept across the role (the old `personal_dirs` name was
unmemorable / semantically vague): `customized_extra_dirs.yml` + schema, scripts
(`gen_customized_extra_dirs_aa_mixins.py`,
`gen_customized_extra_dirs_definitions_yaml.py`), every profile `#include
<abstractions/local_mixin_customized_extra_dirs__for__<category>>` line,
`local_mixin_customized_extra_dirs__DENY_ALL`, `tasks/`, `defaults/`,
`scripts/sandbox/configs/apparmor.py`, docs, and `Makefile`.

## Deprecated all-or-nothing deny mixin removed - done 2026-06-17

The old `local_mixin_deny_personal_dirs` mixin - plus its separate source
`deny_personal_dirs.aa` and the legacy scripts `_gen_deny_personal_dirs.py` /
`_check_deny_personal_dirs.py` - is gone. Replaced by the single-source deny-all
`local_mixin_customized_extra_dirs__DENY_ALL` (generated from
`customized_extra_dirs.yml`, the same source as the per-category abstractions).
`files/profiles/local_mixin_container_base.aa` includes it; the deploy loop in
`tasks/common.yml` globs `local_mixin_customized_extra_dirs__*`.

## Kernel attack-surface hardening (userns / io_uring / caps / network) - in progress

Pin `abi <abi/5.0>` per profile to turn on userns / io_uring / network / mqueue mediation
(pure kernel LSM; kernel 7.0.10 + parser 5.0 support all). Roll out via
`apparmor_profile_mode=complain`, collect denials, then enforce.

CVE rationale: unprivileged userns gates ~44-63% of recent kernel LPEs (CVE-2024-1086
nf_tables, eBPF, io_uring families) and expands kernel attack surface 3.4x; io_uring was
~60% of Google's 2022 kernel-exploit bug-bounty. Deny these for every non-browser app.

userns policy: the 4 browsers (firefox / chromium / msedge / vscode) + glycin (firefox's
forced image-decoder bwrap) get `userns create`; everything else denied.

D-Bus is OUT of scope: the session bus is `dbus-broker`, which does NOT consult AppArmor,
so `dbus` rules are no-ops here. (Would need `xdg-dbus-proxy` [needs bwrap, dropped] or
switching to `dbus-daemon`.)

- [x] `local_mixin_network_deny` (deny egress for image / video / pdf / score viewers)
- [x] `apparmor_profile_mode` var + `aa-enforce` / `aa-complain` toggle in `_install.yml`
- [x] `local_mixin_kernel_surface_browser` (caps sys_admin/sys_chroot/sys_ptrace + userns create)
- [x] `local_mixin_kernel_surface_general_app` (audit deny capability/userns/io_uring/mount/umount/pivot_root/mqueue)
- [x] `local_mixin_network_app` (whitelist inet/inet6/unix/netlink; denies rds/rxrpc/alg -> PinTheft/DirtyFrag/CopyFail)
- [x] abi/5.0 pinned on ALL profiles; browsers -> capabilities_browser; telegram + all viewers + mpv -> deny_kernel_attack_surface; viewers + mpv -> deny_network; telegram/anydesk -> network_app
- [ ] vscode userns: pending `ls -l /usr/share/code/code-sandbox`. If 4755 (SUID) -> split vscode out of capabilities_browser (keep `capability sys_chroot`, drop `userns create`: SUID sandbox stays, userns closed). If 0755 -> keep userns (avoid forcing --no-sandbox).
- [x] glycin: kept (firefox forces it); pinned abi/5.0 + added `userns create` (its bwrap needs it). Keeps inline caps; NOT given deny_kernel_attack_surface.
- [ ] Complain pass -> add audited mount/unix/etc. allows -> flip `apparmor_profile_mode` to `enforce`

## Display-server access: `local_mixin_gui_*` extraction - done 2026-06-10

Every confined GUI app used to inline its own Wayland/X11 display grants; they had drifted
out of sync. Extracted into four mixins (split by what each grant authenticates to, NOT just
by protocol - iceauth turned out to be session-management, not X11 display):

- [x] `local_mixin_gui_wayland` - `wayland-[0-9]*` compositor socket. Unconditional, all 14
  GUI profiles. Low risk (compositor-isolated).
- [x] `local_mixin_gui_session_manager` - `iceauth_*` (ICE / XSMP session manager). Used under
  BOTH Wayland and X11, so UNCONDITIONAL - never behind `apparmor_allow_x11`. Only the libSM
  family (firefox / chromium / msedge / vscode / mpv) includes it.
- [x] `local_mixin_gui_x11` - `xauth_*` + `/tmp/.X11-unix/{,X*}` (X server access, high risk).
  Included inside `{% raw %}{% if apparmor_allow_x11 %}{% endif %}{% endraw %}`. Both socket styles in one mixin: the
  abstract socket is already covered by `network unix` (local_mixin_network_local_ipc), so the
  filesystem path is a redundant second door - no widening.
- [x] `local_mixin_gui_x11_deny` - plain `deny` of the X11 paths (incl. legacy `~/.Xauthority`),
  included in the `{% raw %}{% else %}{% endraw %}` branch. Noise silencer, not a security boundary.

Gate bugs closed by the refactor (found 2026-06-10 while debugging firefox launch):

- [x] X11 gate was bypassed in `chromium` / `msedge` / `vscode` / `mpv` (xauth + iceauth had no
  `apparmor_allow_x11` wrapper) and half-bypassed in firefox. Now `xauth` is structurally
  behind the gate via the conditional `#include`; `iceauth` is intentionally ungated but moved
  to its own `gui_session_manager` mixin (it is session management, not display access).
- [x] firefox launch fix: the stopgap inline `wayland-[0-9]*` is folded into `gui_wayland`.
- [x] `gui_x11_deny` generalises gwenview's lone allow-if-else-deny pattern to every X11 user.

Rationale (iceauth vs xauth, why iceauth is ungated, why the two socket styles share one mixin)
lives in the mixin file headers under `files/profiles/local_mixin_gui_*.aa`.

## anydesk profile drift found 2026-06-10

- [x] `anydesk` was missing `local_mixin_deny_mounted_external_media` - added.
- [ ] `anydesk` still has no `local_mixin_customized_extra_dirs__for__<category>` include. CLAUDE.md
  requires every pathbased profile to include exactly one customized_extra_dirs category. User does not
  currently run anydesk; decide `others` vs a dedicated category, or document the exemption.

## `python3-jsonschema` install: handled by the role itself

`roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py` validates
`roles/apparmor/local_vars/customized_extra_dirs.yml` against a JSON Schema at playbook
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

## `local_pathbased_anydesk` does not include any customized_extra_dirs abstraction

Unlike every other pathbased profile, `templates/anydesk/local_pathbased_anydesk.aa.j2`
does not include the `local_mixin_customized_extra_dirs__DENY_ALL` deny-all or any
`local_mixin_customized_extra_dirs__for__<category>` abstraction. Per the convention now
documented in `roles/apparmor/CLAUDE.md` ("every pathbased profile must
`#include` exactly one"), anydesk should be brought into compliance, most
likely with `__for__others`. Defer until a deliberate review of what anydesk
actually needs - remote-desktop access patterns differ enough that the safest
default may not be the right one.

## seccomp hardened launchers (SECCOMP.md) - in progress 2026-06-23

Implements `roles/apparmor/docs/SECCOMP.md`: a generic `~/.local/bin/seccomp-launch` wrapper +
per-app derived `(hardened)` .desktop that routes a GUI launch through a transient systemd
`--user` service carrying a seccomp syscall denylist (blocks AppArmor-blind LPE primitives).
Complementary to the AppArmor "Kernel attack-surface hardening" section above (that is LSM
mediation; this is the syscall layer). All user-home only - no `become`.

- [x] `files/seccomp-launch`: `env -i` env allowlist (default-deny; blocks `LD_PRELOAD` etc. from
  the shared/mutable systemd `--user` manager env), per-app `extra_env` via leading `VAR=value`
  tokens, seccomp denylist.
- [x] seccomp denylist (group contents verified against systemd `seccomp-util.c`):
  `~userfaultfd perf_event_open keyctl add_key request_key bpf @io_uring @mount @clock @obsolete
  @cpu-emulation @raw-io @swap @reboot @module @debug`. New vs spec: `bpf` (eBPF verifier LPEs),
  `@mount` (new mount API: fsopen/move_mount/mount_setattr LPEs), `@clock`.
- [x] `tasks/seccomp.yml`: deploy wrapper + derive .desktop (read distro entry via `lookup('file')`,
  regex-rewrite `Exec`/`Name`/`DBusActivatable`, write to `~/.local/share/applications/`) +
  missing-source WARN + pre-clobber `THIS_FILE_IS_MANAGED_BY_ANSIBLE__DO_NOT_EDIT_MANUALLY` safety assert + deprecated-id cleanup.
- [x] `defaults/main.yml`: `apparmor_seccomp_launchers` + `_deprecated` lists.
- [x] wired into `tasks/_install.yml`.
- [ ] CONFIRM Telegram's distro .desktop ID on the real host: `ls /usr/share/applications/ | grep -i telegram`.
  `defaults` assumes `org.telegram.desktop.desktop`; fix the entry if different.
- [ ] VERIFY on a real desktop session (sandbox CANNOT - no display, app absent): launch the
  `(hardened)` entry, then `grep Seccomp /proc/$(pgrep -x Telegram)/status` -> `2`.
- [ ] RETIRE old `ansible_telegram.desktop` (in `telegram.yml`) once the derived entry is confirmed
  working. Until then BOTH show in the menu (old "Telegram (AppArmor)" + new "(hardened)").
- [ ] mpv / vlc: add to the list AFTER checking the wrapper does not clash with mpv's aa-exec GPU
  launcher (`local_attachmentless_mpv_gpu`). Media players keep `extra_env` EMPTY (no software GL).
- [ ] Browsers / Electron: intentionally EXCLUDED (self-apply stronger seccomp-bpf to content
  processes; an inherited outer filter can break their sandbox). See SECCOMP.md section 2.
