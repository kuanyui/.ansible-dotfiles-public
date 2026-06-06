# TODO

Durable mirror of the in-session task list (the task tool is local/ephemeral;
this file is the git-tracked, cross-machine source of truth). Keep in sync.

Status: `[ ]` pending · `[~]` in progress · `[x]` done · `[blocked: #N]`

## incus_vm host install/uninstall split + per-user net gap

Triggered by a real `ivm init claude` on a host using the unprivileged `incus`
group (per-user restricted project `user-1000`). Three distinct ivm bugs already
fixed in `files/ivm` (see that diff), then a role-structure refactor:

- [x] **`shift=true` removed from VM mounts** - container-only property; rejected
  by restricted projects, no-op for VMs. (`files/ivm` `mount_commands`.)
- [x] **Socket-path validator** - a valid (<=63) instance name still overflowed
  the virtiofs `AF_UNIX` sun_path (108) once the `user-1000_` prefix + longest
  device suffix were added -> cryptic `incus start` "connect: invalid argument".
  `files/ivm` now models the real socket path at name-pick time and rejects/
  re-prompts (`socket_path_error`, `current_incus_project_prefix`).
- [x] **Rename `tasks/host_setup.yml` -> `tasks/incus_host_install.yml`** (+
  `defaults/main/host_setup.yml` -> `defaults/main/incus_host_install.yml`); all
  refs swept (main.yml, ivm_install, preseed, docs, IMPLEMENTATION_PLAN). The var
  `incus_vm_skip_host_setup` was left as-is (out of scope to rename).
- [x] **Add `tasks/incus_host_uninstall.yml`** - full teardown EXCEPT distro incus
  packages; 7 steps each gated by its own `incus_vm_uninstall_*` toggle (defaults
  in `defaults/main/incus_host_uninstall.yml`, all false = safe no-op, no sudo).
  Wired into `tasks/main.yml` on `incus_vm_state: absent` (gated on
  `not incus_vm_skip_host_setup`). Storage-pool delete and incusbr0 delete are
  SEPARATE toggles (orthogonal). Order encodes incus's referential constraints:
  instances -> user-* projects -> incusbr0 -> default pool -> firewalld -> group
  -> disable daemon (last). NOTE: the `default` pool can't be deleted while a
  `user-*` project's auto default profile still pins it, hence user-projects
  before pool. Verified: YAML parse + `ansible-playbook --syntax-check` on both
  playbooks. NOT run against real incus (only the host can).
- [ ] **per-user net gap (the actual root cause tonight)** - `incus_host_install`
  only fixes `incusbr0` (default project). The unprivileged `incus` group uses
  incus-user's auto-created `incusbr-1000`, which came up with `config: {}` (no
  IPv4) -> VM got IPv6-only -> no default route -> provisioning aborted. Install
  does NOT cover the per-user bridge. DECIDE how the role should handle it.
- [ ] **ivm error msg hardcodes `incusbr0`** - misleads on unprivileged hosts
  (bridge is `incusbr-<uid>`); make it print the VM's actual NIC/network. Offered.

## incus launcher improvements

- [x] **1. Decide launcher language (bash vs Python)** -> **bash now.**
  Python rewrite deferred to the bigger `incus_vm` redesign (presets /
  multi-distro / Windows; see `roles/incus_vm/REDESIGN.md` §4.6),
  where it pays for itself. The bash thrown away by doing #2/#3 now is ~30
  lines; the "test twice" cost is marginal vs a premature 956-line rewrite.

- [x] **2. `init` preview + y/N confirm** before creating a VM.
  Done in the `incus_agents` launcher: `_confirm_create` shows cwd / agent / VM
  name / image / cpu+mem+disk / mounts before `incus launch`, gated y/N; fires
  on ANY create path (init/agent/shell). `-y`/`--yes` skips; non-TTY without
  `--yes` aborts. Validated by rendering + `bash -n`. (Workstations launcher not
  done - its VM name is fixed per entry, not cwd-derived, so lower value; offer.)

- [x] **3. Open an existing VM by name (with completion), no cd needed.**
  Done (agents): `v-<agent> -n <suffix> shell` already targets an existing VM
  without cd (launcher sets HOME/USER/cwd env). Added zsh+bash completion of
  `-n` with the suffixes of existing `v-<agent>-*` VMs (via `incus list`), plus
  `-y`/`--yes` in the flag completion. Validated by `bash -n` / `zsh -n`.
  Workstations N/A (VM name = launcher name, no cwd suffix).

- [x] **4. Makefile `incus-overwrite-dotfiles-in-all-guest`** (our own Linux guests only).
  Done. Both launchers now tag VMs at `incus launch`:
  `user.ansible-managed=true` + `user.ansible-guest-os=linux`. New Makefile
  target pushes user+root staged dotfiles to all `v-*` VMs (type=VM), skips any
  tagged `user.ansible-guest-os=windows`, treats legacy untagged as Linux.
  Added to `.PHONY`; supersedes `resync-incus-agents-dotfiles` (left in place).
  Validated: recipe `bash -n` (with resync as known-good baseline) + both
  launchers render + `bash -n`.

## Follow-ups done (later session)

- [x] **`rma` -> `delete`** in both launchers (incus-native verb, consistent with
  `init`/`start`/`stop`/`snapshot`; `rma`'s "all" overclaimed - base image is not
  removed). Dispatch + help + hints + reserved lists in both `main.yml` updated.
- [x] **`delete` asks y/N first** (destructive: config+disk+snapshots). Agents uses
  `--yes`/`ASSUME_YES` to skip; workstations always asks (no `--yes` flag there).
  Non-TTY aborts.
- [x] **Removed the per-agent subcommand** (`v-<agent> <agent>`); run the agent via
  `v-<agent> shell` then the command inside. `cmd_agent` + its dispatch token gone.
- [x] **Workstations init preview + `--yes`** (deferred from task #2). Added
  `_confirm_create` (VM name, image, cpu/mem/disk, gui, apt pkgs, mounts) before
  `incus launch`; `--yes`/`-y` stripped via a pre-dispatch arg scan (this launcher
  has no flag parser) sets `ASSUME_YES`; non-TTY aborts. Help updated. Validated:
  render (mounts + no-mounts) + `bash -n`.
- [x] **Agents reserved-word assert: KEEP as a defensive guard** (decided). Since the
  agent name is no longer a dispatch token it can't actually collide, but the check
  is harmless and kept for naming hygiene; comment in
  `roles/incus_agents/tasks/main.yml` says so.

## incus_vm engine (`ivm`) - redesign

Phases tracked in `roles/incus_vm/IMPLEMENTATION_PLAN.md`; mirrored here.

- [x] **Phase 0 scaffold** - role installs `ivm` + schema + deps + example
  templates; `ivm --help` / `ivm env` / `--dry-run`.
- [x] **Phase 1 minimal Linux (Debian)** - `ivm init` (validate -> name
  prompt -> launch + `user.*` tags -> mounts -> minimal provision -> push
  dotfiles) + `ivm shell` (cwd-resolve). Default VM name carries `ivm-` prefix.
  Per-os_family dotfiles staging done (`vm-rootfs/<family>/{home/user,root}`).
  Static-verified (mypy --strict, syntax-check, dry-run); needs real incus host
  + `make sandbox-incus-vm` for end-to-end.
- [~] **Phase 2 lifecycle + provision depth** - DONE on the engine side
  (static-verified: mypy --strict, dry-run init/env for Debian + openSUSE):
  start/stop/delete (y/N confirm) / overwrite-dotfiles / update / env (prints
  resolved package list) / set-root-password / unset-root-password;
  `post_install_script` (root, author drops to `su - user`); baseline + groups +
  flat packages resolved & deduped per ansible_os_family; openSUSE/Fedora via
  per-family pkg-mgr (apt/zypper/dnf). Baseline is a registry bundle
  (`distro_packages_incus_guest_baseline`); the registry is materialized to
  `<root>/package-groups.json` at apply time (ivm has no ansible at runtime).
  PENDING: re-run `make sandbox-incus-vm` (verify the `to_nice_json` render +
  per-family staging) and real-incus end-to-end (esp. an openSUSE guest). No
  Fedora template yet (dnf path written but untested).
- [ ] **Verify baseline package names per distro on a real box** - the
  `distro_packages_incus_guest_baseline` per-family overlays were set from web
  search, not a live `zypper`/`dnf`. CONFIRM on Tumbleweed: are
  `zsh-syntax-highlighting` / `zsh-autosuggestions` in the DEFAULT OSS repo? (web
  only found them in the OBS `shells:zsh-users:*` devel project; currently
  OMITTED from the `suse:` overlay, so openSUSE zsh runs without them). Also
  confirm `openssh` (not `openssh-server`) is right for openSUSE sshd. Related:
  the staged `.zshrc` sources the zsh plugins from a path that may differ per
  distro - installing the package is necessary but maybe not sufficient.
- [~] **Phase 3 extras** - DONE (static-verified: mypy --strict + dry-run for
  shadow/tmpfs/ssh/snapshot/gui): `mounts[].shadow` (empty-mask overlay),
  `sys.timezone` (host or literal), `sys.tmpfs` (mount + fstab), `sys.ssh_server`
  (sshd drop-in + authorized_keys + enable), `snapshot` (cwd-resolved passthrough),
  `gui` (`incus console --type=vga`). Unimplemented launch-config now GUARDED
  (dies loudly, no silent downgrade): `hw.gpu`!=none, `hw.tpm`, `hw.secureboot`=false,
  `hw.nested_virt`, `net.mode`!=nat.
  Launch-config tier DONE too (verified against incus docs + dry-run): init now
  does `incus create` (stopped) -> attach devices -> `incus start` so non-
  hotpluggable devices work; `hw.secureboot=false` (--config), `hw.tpm`
  (vtpm device), `net` macvlan/bridge (eth0 nic, needs `net.parent`),
  `hw.nested_virt` (host-gated: no incus config, just warns if host kernel
  nesting looks off). Findings recorded in `roles/incus_vm/docs/incus-hardware-capabilities.md`.
  SCHEMA fixed to reality: removed `hw.gpu` (incus has no virtio-gpu/virgl - its
  QEMU is built without virgl; passthrough needs a PCI addr + host VFIO, out of
  scope) and updated `hw.nested_virt` description. windows11.yaml lost its gpu block.
  Parent-dir resolution DONE (REDESIGN 8.9): `resolve_vm_by_cwd` walks ancestors -
  in a subdir of an init'd project it prompts "open '<vm>' init'd at <parent>? [Y/n]"
  (non-TTY: errors with the hint). Two-level shell completion DONE (zsh `_ivm` +
  bash `ivm`, installed to `incus-vm/{zsh,bash}-completions/`, auto-discovered by
  the rc globs; functionally tested: subcommands, then template names for
  init/env). PHASE 3 COMPLETE.
  Note: the staged `.zshrc` sources the zsh plugins via `[ -f ... ]` guards, so a
  distro with a different path (or openSUSE, which omits them) just skips them
  gracefully - non-blocking; Debian/Fedora paths match.
- [~] **Phase 4 retire `incus_agents`** - migrate claude/codex to `ivm`; remove
  the old bash launchers.
  PREP DONE (non-destructive): ivm templates now cover both agents incus_agents
  runs - `claude.yaml` (curl install) + new `codex.yaml` (apt nodejs/npm + `su -
  user` npm install -g @openai/codex), both schema-validated. So `ivm init
  claude` / `ivm init codex` are ready.
  Step 1 DONE (user OK'd destructive; single-host, recoverable): retired
  `incus_agents` - git rm the role + both playbooks + sandbox config; removed its
  Makefile targets (apply/check/unapply/sandbox + resync-dotfiles) + .PHONY
  tokens; dropped its branch from `incus-overwrite-dotfiles-in-all-guest` (now
  filters guests by `user.ansible-managed` tag, not `^v-` name); removed
  `setup_incus_agents` from group_vars; removed the incus-agents row from the
  CLAUDE.md namespace table; rewrote the README (tree, role table, completion
  example, the dedicated section) for `ivm`. Verified: remaining playbooks
  syntax-check, sandbox config instantiates, `make help` clean, zero functional
  refs left (only comments in the `_incus_*` roles, cleaned in Step 2).
  Step 2 DONE: folded BOTH `_incus_*` roles into `incus_vm` (discussed: no second
  incus consumer - ivm is a general engine, new uses are templates not roles;
  incus containers not worth it vs podman -> docs/incus-vs-podman.md).
  `_incus_guest_setup_dotfiles` -> `tasks/{stage_dotfiles,_stage_family}.yml`
  (include_role -> include_tasks; vars `incus_guest_setup_dotfiles_*` -> `incus_vm_dotfiles_*`).
  `_incus_host_setup` -> `tasks/host_setup.yml` + storage-pool vars into
  `defaults/main.yml` + `incus_preseed.yml.j2` into `templates/` + its README ->
  `docs/incus-host-setup.md` (348 lines preserved, refs de-agented). Both role
  dirs deleted. Fixed all broken links (main README, incus_vm README, preseed).
  Verified: incus_vm syntax-check, sandbox instantiates, mypy.
  Step 3 DONE (layout reorg): all ivm data nested under `incus-vm/ivm/`, prefixes
  dropped - `template.schema.json`, `templates/`, `rootfs/<family>/`,
  `package-groups.json`; `ivm --root`/`DEFAULT_ROOT` = `incus-vm/ivm` (ansible var
  `incus_vm_ivm_dir`); `{zsh,bash}-completions/` stay SIBLINGS at `incus-vm/`.
  Also renamed task/defaults files for clarity (`install.yml`->`ivm_install.yml`,
  `uninstall.yml`->`ivm_uninstall.yml`) and scrubbed the vague invented word
  "engine" everywhere (code + all docs) -> `ivm`/"launcher". Verified: mypy,
  dry-run init/env on the nested layout, syntax-check, sandbox, completion -n.
  PHASE 4 essentially COMPLETE. Remaining: (a) real-incus end-to-end of ivm (only
  the user's host can), (b) the stale-docs item below.
- [x] **Stale docs** - DONE: rewrote `roles/incus_vm/README.md` for `ivm`
  (templates, subcommands, VM identity, provisioning model, new file layout,
  doc links) and fixed the `make apply/unapply/sandbox-incus-vm` help strings
  (no more `v-<workstation>` / manifest / `rma`).

## GUI + CJK package groups (ivm)

- [x] **`sys.input_method: fcitx5`** - ivm writes the IM env vars
  (`GTK_IM_MODULE`/`QT_IM_MODULE`/`XMODIFIERS`) to `/etc/environment` (X11 +
  Wayland universal); `sys.gui` now installs `spice-vdagent` + `xdg-user-dirs`.
  Schema field added; gui-gated. Static-verified (mypy, dry-run, schema).
- [x] **`cjk_fonts` / `cjk_input` groups** - Noto Sans CJK (one pan-CJK font;
  Suse uses `-jp-` variant, Debian/Fedora the combined pkg) + fcitx5 + mozc +
  chewing + gtk/qt frontends. Per-family names diverge; Suse verified on
  Tumbleweed.
- [x] **`gui_x11` / `gui_wayland` groups** - X11 stack (server + startx + xauth +
  libinput input driver) and Xwayland-only Wayland base; WM/DE + display-manager
  stay per-template. Names web-verified per family (default repos).
  `webbrowser.yaml` switched to `gui_x11`. Static-verified (Suse resolution,
  schema). The libinput driver was added after a real run showed the desktop
  rendering but the mouse not clicking (no X input device without it). Video
  needs no package - the server's modesetting drives virtio-gpu/std-VGA.
- [ ] **Verify `cjk_input` names on real Debian/Fedora** - Debian
  `fcitx5-frontend-gtk4`/`-qt6` + `fcitx5-config-qt`; Fedora umbrella
  `fcitx5-gtk`/`fcitx5-qt` (vs per-toolkit split). Set from web search, not a
  live `apt`/`dnf`.

## ivm real-run fixes + desktop UX

First real `ivm init webbrowser` on the host surfaced these (all fixed unless noted):

- [x] **`init` failure: no auto-delete, no traceback** - wrap post-create steps
  in try/except; on failure print a clean message + recovery commands (inspect /
  remove / rebuild), leave the VM in place (transient mirror/network blips
  shouldn't nuke a likely-fine VM).
- [x] **`wait_ready`: also wait for network online** - provisioning was racing a
  not-yet-configured network (zypper refresh -> curl error 7). Now waits for a
  default route + DNS (`getent hosts example.com`) before provisioning.
- [x] **GUI VMs reboot after provisioning** - `set-default graphical.target` +
  enable DM only take effect on next boot, so a `sys.gui` VM rebooted into a TTY.
  Engine now `incus restart`s gui VMs post-provision (autologin + IM env apply).
- [x] **zypper default `-vvv`** - zypper is failure-prone; max verbosity by
  default so failures are diagnosable from the init log (constant `ZYPPER`).
- [x] **`init`/`delete` preview: network + mounts + storage pool** - three
  `preview_*` helpers; storage pool best-effort from `incus storage info`.
- [x] **`gui_x11` libinput** + **webbrowser `systemctl enable --force lightdm`**
  (openSUSE pre-aliases display-manager.service) + **`icewm-theme-branding`**
  (openSUSE-only theme).
- [x] **`set-root-password` -> 4 commands** - `set-password <username>` /
  `unset-password <username>` (login password, any account) + `enable-user-sudo`
  / `disable-user-sudo` (the `Defaults:user rootpw` escalation, now separate).
- [x] **fcitx5 setup as a shared script** - `setup-fcitx5-input.sh` in
  `roles/incus_vm/files/`. SURGICAL + idempotent: `set_conf_key` sed-replaces (or
  appends) only chewing `SelectionKey=asdfghjkl;` / `PageSize=10` /
  `SpaceAsSelection=True`, preserving every other key; the profile
  (keyboard-us+mozc+chewing) is written ONLY when those IMs aren't already
  enabled, so an already-configured host profile is left untouched. mozc's binary
  config not touched. The engine embeds + runs it as `user` in a
  `sys.input_method: fcitx5` guest (replaced the inline profile heredoc).
- [ ] **fcitx5 host-side wiring (deferred)** - guest is automatic; on the host you
  run the installed copy yourself (`sh <ivm-root>/setup-fcitx5-input.sh`). If the
  manual step gets annoying, promote to a dedicated `roles/fcitx5` (parallel to
  `roles/zsh`/`emacs`, added to `playbooks/user.yml`) so the host auto-configures.
- [x] **Global `--name <vm>`** - target an existing VM by name, ignoring the cwd
  binding (all VM-acting subcommands). Resolved once in `main()` and passed to
  each cmd (they no longer self-resolve). zsh + bash completion of `--name`
  values from `incus list`.
- [x] **`ivm list` + `ivm reboot`** - `list` = raw `incus list` passthrough
  (via `parse_known_args` so `--format` etc. reach incus; other subcommands still
  reject unknown args); `reboot` = `incus restart` the target VM.
- [ ] **Light-desktop apps on icewm** - add `pcmanfm-qt` + `lximage-qt` (the
  actively-maintained LXQt file manager + image viewer; GTK `pcmanfm`/`gpicview`
  are stalled/abandoned). Both in Tumbleweed OSS. DECIDE: extend `webbrowser`
  into a light desktop vs a separate `desktop` template. Deferred - user is
  trying the current setup first to see if needed.
- [ ] **Cross-distro icewm theming** - when a non-openSUSE icewm template exists:
  Fedora `+= icewm-themes` (extras; default theme already in `icewm` since F31),
  Debian has none (bundled), and ship a `~/.icewm/theme` pick so it's not ugly on
  all three (a dotfile, same spirit as the fcitx5 script).
- [x] **GUI bare-WM autostart convention** - `ivm` installs `spice-vdagent` (for
  `sys.gui`) but doesn't autostart it; on a bare WM (icewm, which ignores XDG
  autostart) the template must launch `spice-vdagent &` (clipboard) + `fcitx5 -d &`
  (IME) from the WM startup. Added spice-vdagent to webbrowser's icewm startup;
  documented the rule in the `sys.gui` schema description. DEs (KDE/GNOME/LXQt)
  autostart both via XDG. (Clipboard is SPICE-bidirectional once the agent runs;
  toggle off via remote-viewer's share-clipboard pref or by not starting it.)
- [ ] **`make` universal in `incus_guest_baseline`** - `git` is already in the
  baseline (every guest); `make` is only in `basic_tools`. User uses `make`
  everywhere, so add `make` to `incus_guest_baseline.common` -> every guest gets
  git+make regardless of groups. (claude already gets make via its `basic_tools`
  group; this just makes it baseline-universal.) Keep `make` in `basic_tools` too
  for the HOST path (baseline is guest-only); resolve dedupes on guests. One-line
  change - offered to do immediately.
- [ ] **`qtdev` environment - draft the group(s) + template** - C++ dev toolchain
  + Qt. User uses: QWidget, QtConcurrent, QtMultimedia, QML (Qt Quick). Likely a
  GUI VM (QWidget/QML need a display). DESIGN OPEN:
  - Split a reusable `cpp_dev` (gcc-c++/cmake/gdb/ninja/pkgconf) group from a
    `qt_dev` (Qt6 modules) group, vs one combined group. Lean split (cpp_dev
    reusable for non-Qt C++).
  - Qt6 module -> openSUSE Tumbleweed `-devel` package mapping TO VERIFY (don't
    guess): qtbase/QWidget+QtConcurrent `qt6-base-devel`, QtMultimedia
    `qt6-multimedia-devel`, QML/Quick `qt6-declarative-devel`; build glue
    `cmake`/`qt6-tools`. Optionally `qt-creator` IDE. Per-family (apt/dnf) names
    diverge - verify each.
  - Decide: define in `roles/distro_packages/defaults/main.yml` as group(s)
    (reusable, like cjk_input) + a `qtdev.yaml` template referencing them.
  - Note: `pcmanfm-qt`/`lximage-qt` are runtime Qt APPS (no -devel); orthogonal
    to qtdev, classify separately (light-desktop apps item above).

## Notes / future

- [ ] **container_apps -> one engine + declarative templates** (parallel to what
  `ivm` did to incus_agents). DESIGN written: `roles/container_apps/REDESIGN.md`.
  Replaces the rendered `c-<tpl>-<rt>` launchers + 454-line `host-cli.sh.j2` +
  manifest with one Python engine (working name `capp`, TBD); reuses `roles/zsh`
  for dotfiles (kills `container_templates`'s own zshrc/bashrc.j2); folds
  `container_templates` into the engine role. Big, separate effort. Also: `git rm
  --cached roles/container_templates/filter_plugins/__pycache__/*.pyc` (committed cruft).
- Python launcher rewrite: deferred to the `incus_vm` redesign (see
  `roles/incus_vm/REDESIGN.md`). Trigger = presets / multi-distro /
  Windows. The 11 duplicated subcommands across the two launchers get unified
  there.
- Runtime-unverifiable here (no incus in this env): the `root -> /` push landing
  at `/root`, and `incus list/config get` filtering. Logic is sound; confirm on
  a real incus host.
