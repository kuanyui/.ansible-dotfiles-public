# TODO

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
- [ ] `anydesk` still has no `local_mixin_personal_dirs__for__<category>` include. CLAUDE.md
  requires every pathbased profile to include exactly one personal_dirs category. User does not
  currently run anydesk; decide `others` vs a dedicated category, or document the exemption.

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
