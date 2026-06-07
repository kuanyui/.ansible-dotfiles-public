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
- [x] **Makefile targets** - `incus-uninstall-ivm` help corrected (ivm-only now);
  added `incus-teardown-host` (DESTRUCTIVE, `--ask-become-pass`, all toggles
  except group removal) driven by overridable `INCUS_VM_HOST_TEARDOWN_FLAGS`;
  added to `.PHONY`. Verified via `make -n incus-teardown-host` + `make help`.
- [x] **per-user net gap (the actual root cause)** - the unprivileged `incus`
  group uses incus-user's auto-created `incusbr-<uid>`, which on this host came up
  with `config: {}` (no IPv4) -> VM got IPv6-only -> no default route ->
  provisioning aborted. ALSO: the preseed init is skipped when a `default` pool
  already exists (its `when:` guard). This host has a hand-made `dir` `default`
  pool (observed: ivm preview `storage pool: default (dir)`; matches branch name
  "without manually create loop file") so the preseed's `incusbr0` was never
  created (confirmed: `incus network list` showed only `incusbr-1000`).
  FIX in `incus_host_install.yml`
  (replaces the earlier "set incusbr-<uid> ipv4" attempt): (1) ensure `incusbr0`
  exists with IPv4 NAT independently of preseed; (2) trigger `user-<uid>` project
  creation; (3) grant it `restricted.networks.access=incusbr0[,incusbr-<uid>]`
  and repoint the project default profile `eth0` to `incusbr0`. Routes per-user
  VMs through the standard bridge instead of fighting the flaky auto one.
  NON-FATAL on the per-user steps. Uninstall already reverses it
  (`delete_incusbr0_network` + `delete_autocreated_user_projects`). Verified: YAML
  + syntax-check; NOT run against real incus.
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

- [x] **4. Makefile `incus-push-dotfiles`** (our own Linux guests only).
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
  + `make incus-sandbox` for end-to-end.
- [~] **Phase 2 lifecycle + provision depth** - DONE on the engine side
  (static-verified: mypy --strict, dry-run init/env for Debian + openSUSE):
  start/stop/delete (y/N confirm) / overwrite-dotfiles / update / env (prints
  resolved package list) / set-root-password / unset-root-password;
  `post_install_script` (root, author drops to `su - user`); baseline + groups +
  flat packages resolved & deduped per ansible_os_family; openSUSE/Fedora via
  per-family pkg-mgr (apt/zypper/dnf). Baseline is a registry bundle
  (`distro_packages_incus_guest_baseline`); the registry is materialized to
  `<root>/package-groups.json` at apply time (ivm has no ansible at runtime).
  PENDING: re-run `make incus-sandbox` (verify the `to_nice_json` render +
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
  tokens; dropped its branch from `incus-push-dotfiles` (now
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
  doc links) and fixed the `make incus-*` help strings
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
- [x] **`snapshot` sub-action completion** - zsh `_ivm` + bash `ivm` now complete a
  THIRD level under `snapshot`: the `incus snapshot` actions (create/list/restore/
  delete/rename/show), then for restore/delete/rename/show the target VM's EXISTING
  snapshot names (`incus snapshot list`; VM resolved by `--name`, else `incus list
  user.ivm_init_at_dir=$PWD`). create's name slot + rename's 2nd arg correctly offer
  nothing. Also fixed the stale `(create/list/restore/delete)` blurbs (`_ivm` describe
  + `ivm` `CWD_RESOLVED_HELP`) to add rename/show. Functionally tested: bash via a
  stubbed `incus` (10 cases), zsh via a real interactive-TAB `zsh/zpty` harness.
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

## ivm CLI/UX polish

Surfaced using `ivm` interactively. All DONE (notes per item). Static checks:
`py_compile` + a focused unit harness (importlib-loaded `ivm`, stubbed
incus/tty/input - 23 cases) + CLI dry-run smoke. `mypy --strict` NOT run (no
pip/mypy in this env - run it on the host); NOT exercised against real incus.

- [x] **Color the VM name in `ivm` output** - the instance name is hard to pick
  out of the stderr wall (`+ incus ...` echoes, confirm previews, `==> <name>
  ready/running`, `info`, the cwd-resolve prompts). Colorize the name everywhere
  ivm prints it, via ONE helper (e.g. `colorize_vm_name`) called at each print
  site - don't scatter raw escape codes. Gate on `sys.stdout.isatty()` + honor
  `NO_COLOR` so piped / non-TTY output stays plain (same TTY-gating spirit as
  `resolve_vm_by_cwd` / `confirm_*`).
  **DONE:** `colorize_vm_name(name, *, stream=sys.stderr)` (bold-cyan) + consts
  `VM_NAME_COLOR`/`COLOR_RESET`; gated `os.environ.get("NO_COLOR")` +
  `stream.isatty()`, per-stream (stderr default; `info` passes `sys.stdout`). 13
  call sites (confirm name field, every `==>` status line, `info`, resolve prompts
  + the selector listing); raw `+ incus ...` echoes left plain (copy-pasteable).

- [x] **`ivm gui` should detach from the calling shell by default** - `cmd_gui`
  (`files/ivm:1229`) currently does `exec_into(["incus", "console", "--type=vga",
  name])`, which `os.execvp`-replaces ivm with a FOREGROUND process tied to the
  terminal: closing the terminal kills the GUI and its stdout/stderr clutters the
  shell. Make gui launch detached - own session, stdout/stderr to `/dev/null` -
  so the terminal can be closed safely (likely `subprocess.Popen(...,
  start_new_session=True, stdout=DEVNULL, stderr=DEVNULL)` instead of
  `exec_into`). VERIFY FIRST (per CLAUDE.md, web the incus docs): what `incus
  console --type=vga` actually spawns - does it fork a SPICE viewer and return,
  or stay attached? - that decides the right detach mechanism. Consider a
  `--attach`/foreground escape hatch.
  **DONE:** `cmd_gui` now `subprocess.Popen(start_new_session=True,
  stdin/stdout/stderr=DEVNULL)` instead of `exec_into`. Web-checked
  `cmd/incus/console.go vga()`: viewer is remote-viewer else spicy, and with
  NEITHER it does NOT error - it prints a socket path and HANGS; so a
  `shutil.which` pre-flight dies loudly (install hint) rather than leave an
  invisible stuck process. vga needs no TTY (only text console sets raw mode), so
  DEVNULL stdin is safe. No `--attach` (YAGNI; die msg points at `incus console
  --type=vga <vm>` to debug). README + `gui` help blurb updated.

- [x] **Multi-VM-per-cwd selector** - multiple VMs CAN bind to one cwd: explicit
  `ivm init <tpl> <name>`, or different templates - both get tagged
  `user.ivm_init_at_dir=<cwd>` by `create_command` (`files/ivm:465`). But
  `resolve_vm_by_cwd` (`files/ivm:778`) builds a dict keyed by init_dir, so >1
  match SILENTLY collapses to the last in incus's CSV order - `ivm
  shell`/`info`/every cwd-resolved subcommand picks an ARBITRARY VM with no
  warning. Fix (one function): collect ALL matches as a list; ==1 -> use it; >1
  -> TTY: print a numbered menu to pick, non-TTY: `die` listing the candidates +
  require `--name` (keeps non-interactive predictable). Apply the same >1
  handling to the ancestor-dir branch (`files/ivm:795`). List each candidate with
  `user.ivm_template` + status, not just the name (names alone are cryptic). Only
  escape hatch today is the global `--name <vm>` (`main:1401`).
  **DONE:** `list_vm_bindings()` returns a `list[VmBinding]` (NamedTuple
  name/status/template/init_at_dir) from `incus list --columns
  n,s,config:user.ivm_template,config:user.ivm_init_at_dir` - no more last-wins
  dict. ==1 at cwd -> use it; >1 -> TTY `choose_vm_from_candidates` numbered
  picker / non-TTY `die_ambiguous` (lists candidates, requires `--name`);
  ancestor-dir branch gets the same >1 handling. Candidates shown as `name
  [template=…, STATUS]`.

## trusted_pubkeys role (built; SSH verified, GPG needs a gpg-host run-test)

Auto-import a small set of well-known public keys for the CURRENT USER only (per
request; no system-wide trust). NOTE: this is a config-style face role (writes
standard dotfiles like `zsh`/`emacs`), NOT a tool role - so NO
`~/.local/share/ansible-managed/` namespace subdir. Wired into `playbooks/user.yml`,
gated by `setup_trusted_pubkeys` (default false in `group_vars/all.yml`).

The user lumped two DIFFERENT key types - they serve different purposes and land
in different places; keep them separate:

- [x] **SSH host keys (GitHub, GitLab) -> `~/.ssh/known_hosts`** - DONE + verified.
  `roles/trusted_pubkeys` built: pinned full key lines in `vars/main.yml`, applied
  per (host,key) via `ansible.builtin.known_hosts` (core module; merges without
  clobbering the user's own entries, allows multiple keys per host, idempotent).
  All 6 keys pinned (GitHub + GitLab x ed25519/ecdsa/rsa); fingerprints verified
  2026-06-08 against published values (GitHub docs + `api.github.com/meta` cross-
  check; GitLab docs). Verified end-to-end on a throwaway `target_home`: syntax-
  check, run1 changed / run2 changed=0 (idempotent), gating works for boolean AND
  string inputs, `.ssh`=0700 / `known_hosts`=0644, `ssh-keygen -lf` of the installed
  file matches the pinned fingerprints. NOT yet run on the user's real host.
- [x] **GPG signing keys (Debian CD/install-media signing) -> DEDICATED keyring**
  - DONE (built). User chose a dedicated keyring (option A) over the main `~/.gnupg`
  pubring: `~/.gnupg/ansible-trusted-debian-cd.gpg` (`trusted_pubkeys_debian_cd_keyring`
  in defaults) - the file IS the ansible-managed marker, uninstall = `rm` it. Verify
  a Debian image: `gpg --no-default-keyring --keyring <that> --verify SHA256SUMS.sign
  SHA256SUMS`. 3 keys pinned armored in `files/` (`988021A964E6EA7D` +
  `DA87E80D6294BE9B` "Debian CD signing key", `42468F4009EA8AC3` "Debian Testing CDs
  Automatic Signing Key"); manifest + source URL (debian.org/CD/verify) in
  `vars/main.yml`. `tasks/import_debian_cd_keys.yml`: detect `gpg` (visible warn +
  skip if absent), import-if-fingerprint-absent, then ASSERT each expected fpr is in
  the keyring (apply-time pin integrity, fails loudly). BUILD-TIME VERIFY despite no
  sandbox gpg: wrote a pure-Python OpenPGP v4 fingerprint checker - all 3 pinned keys'
  computed fpr == expected, structure confirmed (UID + self-sig + subkey). Keys are
  full keyserver.ubuntu.com dumps (complete/functional; minimal keys.openpgp.org
  exports were UID-stripped -> gpg would reject, so rejected that source).
- [x] **Dedicated entry + Makefile targets** - `playbooks/trusted_pubkeys.yml` (sets
  `target_*` like `user.yml` + `setup_trusted_pubkeys: true` to bypass the gate) plus
  `make apply-trusted-pubkeys` / `make check-trusted-pubkeys` (parity with the
  apply-/check- pattern of apparmor/container_apps); added to `.PHONY` + the README
  playbook tree. Verified: `make -n` both, `make help` lists them, syntax-check, and
  the dedicated playbook is idempotent (run2 changed=0). No `sandbox-trusted-pubkeys`
  yet (deferred; role already locally verified - add if a sandbox dry-run is wanted).
- [x] **DECIDED: PIN the keys (hardcode in-repo) - this is the user's intent, for
  audit.** Correct call: they're PUBLIC (no secret to leak, committing is fine -
  the CLAUDE.md path/secret rules don't apply) and pinning gives INTEGRITY -
  reviewed once, frozen, any change shows in `git diff`. The rejected alternative
  (fetch + overwrite each apply) would trust DNS+TLS EVERY run, so a hijacked fetch
  could silently swap in an attacker's key -> MITM of future `git clone`, defeating
  the point of pinning a host key. Rotation is rare so pinning is cheap: GitHub's
  RSA key rotated EXACTLY ONCE (2023-03-24, private key leaked to a public repo),
  ECDSA/Ed25519 never; Debian CD keys roll per stable release and are ADDITIVE (old
  keys still verify old ISOs). Treat a rotation as a deliberate reviewed pin-bump;
  the loud SSH "HOST IDENTIFICATION CHANGED" failure is the wanted signal.
- [ ] **Run-test the GPG path on a gpg-equipped host** - the Claude Code sandbox has
  NO gpg, so only the gpg-ABSENT branch was exercised here (warn + skip cleanly; SSH
  unaffected; `failed=0`). On a real host confirm: import into the dedicated keyring,
  the fingerprint asserts pass, and an actual `gpg --no-default-keyring --keyring
  ~/.gnupg/ansible-trusted-debian-cd.gpg --verify SHA256SUMS.sign SHA256SUMS` of a
  downloaded Debian image succeeds. Then re-run to confirm idempotency (import skipped
  when fingerprints already present).
- [x] **Idempotency (SSH)** - DONE: the `known_hosts` module is idempotent
  (verified run2 changed=0) and merges without clobbering the user's own entries;
  the disabled path prints a visible skip-debug (transparency rule). GPG-import
  idempotency lands with the GPG part (`gpg --import` is naturally idempotent).

## firefox_tunes role (built + verified on a fake profile tree; needs a real-Firefox run)

Apply `about:config` tweaks (mainly disk-cache, to cut SSD writes) to ALL Firefox
profiles of the current user. Config-style role (writes per-profile dotfiles);
wire into `playbooks/user.yml`, gate `setup_firefox_tunes` (default false).

- [x] **RESOLVED (verified, Mozilla docs + support forum): use `user.js` per
  profile.** Three external mechanisms exist; `user.js` is the right one here:
  - **`user.js`** (in each profile dir) - read at EVERY startup, initializes the
    listed prefs to your values; an in-session about:config edit reverts on next
    restart. Sets the EXACT prefs you'd set by hand, just declarative + reapplied -
    this is the "permanent, like manual" method asked for. Profile-level (not
    install-level), needs NO root. <- this role's method.
  - **`policies.json`** (`Preferences` policy; Linux `/etc/firefox/policies/` or
    `<install>/distribution/`) - can LOCK prefs, BUT Mozilla intentionally blocks
    many prefs from being set this way ("avoid people messing with settings... that
    could impact the browser negatively"), so not every about:config key works.
    System/install-level -> awkward for a per-user, no-root role.
  - **AutoConfig** (`mozilla.cfg` + `autoconfig.js` in `defaults/pref`) - most
    powerful: `lockPref()` sets/locks ANY pref incl. ones policies.json refuses, but
    lives in the read-only INSTALL dir -> system-wide, not per-user.
  Do NOT edit `prefs.js` directly (Firefox overwrites it on exit).
- [x] **Enumerate profiles** - DONE (native only). `tasks/apply_user_js.yml` slurps
  `~/.mozilla/firefox/profiles.ini`, `regex_findall('^Path=(.+)$', multiline=True)`,
  prepends the firefox dir to relative paths (`^(?!/)` zero-width replace; an absolute
  IsRelative=0 path is left as-is), writes `user.js` into each. No profiles.ini ->
  visible warn + skip (Firefox not installed / never launched).

- [x] **Prefs to write** - DONE (rendered from `templates/user.js.j2`) + web-verified
  current (Firefox ~v140; the v73-era notes still hold). KEY FINDING:
  `browser.sessionstore.interval` is the #1 idle SSD-write lever (recovery.jsonlz4
  every 15s default) -> default set to 1800000 (30min); clean shutdown still saves
  immediately. `parent_directory` needs a String AND a pre-existing dir (Firefox
  won't create it). All values are overridable `defaults/main.yml` knobs. Original
  notes' prefs (kept as reference):

  | pref | value | note |
  | --- | --- | --- |
  | `browser.cache.disk.smart_size.enabled` | `false` | MUST be false before `capacity` takes effect |
  | `browser.cache.disk.capacity` | KiB, e.g. `1048576` | disk cache size cap |
  | `browser.cache.disk.parent_directory` | path string | dir must exist / be writable; create manually |
  | `browser.sessionstore.interval` | ms, `> 15000` | fewer session-restore writes (default 15000) |

  RAM-cache variant (host RAM >= 16 GB; skip disk cache entirely):

  | pref | value |
  | --- | --- |
  | `browser.cache.disk.enable` | `false` |
  | `browser.cache.memory.enable` | `true` |
  | `browser.cache.memory.capacity` | `-1` (auto) or e.g. `204800` KiB |

- [x] **Keep cache off the SSD** - DONE. `firefox_tunes_cache_strategy` (default
  `ram`, per user's "a+b switchable, default a"): (a) `ram` = `browser.cache.disk.
  enable=false` + memory cache (no disk cache, no dir to manage); (b) `tmpfs_disk` =
  disk cache `parent_directory` on a `/tmp` tmpfs dir. (b) also drops
  `~/.config/user-tmpfiles.d/firefox-tunes-cache.conf` (`d <dir> 0700 ...`) so the
  systemd USER instance recreates the dir each boot (verified: systemd 257 ships
  `systemd-tmpfiles-setup.service` in the user dir + `--user`); the role also creates
  it now. Switching back to `ram` removes that tmpfiles entry.
- [x] **Apply semantics** - DONE: prints "restart Firefox to apply" + the profile
  count. (No "Firefox is running" warning - user.js is harmless to write live, just
  applies next launch.)
- [x] **Wiring + verification** - `playbooks/firefox_tunes.yml` + `setup_firefox_tunes`
  (default false) + `make apply-firefox-tunes` / `check-firefox-tunes` (+ `.PHONY`,
  README role-table + playbook tree), same pattern as trusted_pubkeys. Verified
  end-to-end on a FAKE `profiles.ini` + 2 profile dirs in a temp HOME: syntax-check;
  ram run1 changed / run2 changed=0 (idempotent); BOTH profiles get user.js;
  tmpfs_disk writes `parent_directory` + creates the tmpfs dir + the user-tmpfiles.d
  entry; no-profiles warn+skip; `make -n` both targets.
- [ ] **Real-Firefox run** - NOT exercised against an actual Firefox (sandbox has
  none). On a real host confirm: Firefox picks up the per-profile user.js (the prefs
  show as set/locked-to-value in about:config), and for `tmpfs_disk` a `cache2/`
  actually appears under the `/tmp` dir. Re-run to confirm idempotency.

## install sources: `thirdparty_software` provider + `ivm provision` (planned)

Two axes: WHAT to install (composable named sets) vs HOW (install method). The
distro axis is DONE (`distro_packages` bundles + `_install_distro_packages`
executor + `ivm` reading the materialized JSON). Gaps: non-distro sources
(vscode/claude/npm) are stuck ad-hoc in each template's `post_install_script`
(not reusable), and there's no way to add software AFTER `init`. Decisions from
the design chat: keep `distro_packages` (do NOT rename to a vague
`install_packages`); add ONE sibling provider for everything non-distro; expose
an imperative `ivm provision`. Phased.

- [x] **Phase 1a: `thirdparty_software` provider** - new registry (sibling to
  `distro_packages`) for all non-distro installs: 3rd-party repo (vscode),
  `curl|bash` (claude), npm/pip (codex) - all are "run a shell snippet as root."
  Per-family but **OVERRIDE, not additive** (use host/guest family key if
  present, else `common`; UNLIKE `distro_packages` which concatenates
  common+family - a piece of software has one install method, maybe varying by
  family - document this difference in the docstring). Shape (probe lives WITH
  its script):

  ```yaml
  thirdparty_software_vscode:        # repo type: per-family
    debian: { already_installed: command -v code, install_script: "<add MS keyring + sources.list.d>; apt-get install -y code" }
    suse:   { already_installed: command -v code, install_script: "<rpm --import + zypper ar>; zypper --non-interactive install code" }
  thirdparty_software_claude:        # same everywhere: common only
    common: { already_installed: "su - user -c 'command -v claude'", install_script: "su - user -c 'curl -fsSL https://claude.ai/install.sh | bash'" }
  ```

  `already_installed` OPTIONAL (omit = always run), runs as ROOT (so user-scope
  checks need `su - user -c ...`), use `command -v` not `which`. vscode's snippet
  must ADD THE REPO (not fetch a one-off `.deb`) so `ivm update` keeps it current.
  Executor: HOST = an `_install_*` role analog to `_install_distro_packages`
  (become + run snippet + probe-skip); GUEST = `ivm` reads it from a materialized
  JSON (same mechanism as the distro groups -> `distro-package-groups.json`) and
  runs via `incus exec <vm> -- bash -c`. Migrate claude/codex/webbrowser's
  `post_install_script` installs into entries. codex's npm install must honor
  `centralize_lang_pkgs_dir` (today it hardcodes `npm config set prefix
  ~/.local/npm_global` - see the rename section).
  **DONE:** `roles/thirdparty_software/` (defaults + README, data-only role);
  `ivm_install.yml` materializes -> `thirdparty-software.json`; `ivm` gains
  `load_thirdparty_software` + `resolve_thirdparty_software` (OVERRIDE: family else
  `common`) + `thirdparty_install_script` (probe-guarded `if {probe}; then skip;
  else install; fi`), wired into `provision_script` BEFORE `post_install_script`;
  schema `thirdparty_software[]` field (+ windows exclusion + desc); `ivm env`
  shows it; claude.yaml + codex.yaml migrated off `post_install_script`. Verified:
  `py_compile`, `mypy --strict` 0 errors, `ansible-playbook --syntax-check`, 24
  unit/integration checks (registry rendered from the REAL defaults, jsonschema-
  validate all 4 templates, override/fallback/unknown/no-recipe error paths, probe
  guard, `provision_script` injection, missing-JSON clean die). NOT done: real-
  incus end-to-end (host only); HOST executor role (no consumer yet); `vscode`
  entry (needs web-verified MS repo - infra is ready); codex npm prefix stays
  `~/.local/npm_global` until the rename. When adding a recipe: define it in the
  role defaults AND the `ivm_install.yml` render dict (explicit, like the distro
  bundles).

- [x] **Phase 1b: `ivm provision <name...>`** - install named units onto an
  EXISTING VM (cwd-resolved or `--name`), so software can be added after `init`.
  Phase 1 resolves each name against `distro_packages` bundles + `thirdparty_
  software` entries DIRECTLY - **no new "groups" registry needed yet** (that's
  only for multi-kind bundles; phase 2). Idempotent (apt/zypper natural +
  `already_installed`). zsh+bash completion of the unit names (union of the two
  registries) - REQUIRED, it's how you discover what's installable. Verb decision:
  **`provision`** - `install` is vague (install what? incus?), `profile` clashes
  with incus's own `profile` concept; `provision` ties to ivm's existing
  provisioning step and is unambiguous (`add`/`setup` were the alternatives, easy
  rename if reconsidered).
  **DONE:** `cmd_provision` (added to `CWD_RESOLVED` + handler + a `provision`
  subparser with `names` nargs=+ + main dispatch): classifies each name as a
  `distro_packages` bundle or a `thirdparty_software` recipe, resolves per the VM's
  `user.ivm_ansible_os_family` tag, builds ONE root script (distro install +
  probe-guarded thirdparty) run via `incus exec`; unknown name dies listing both
  registries. `resolve_thirdparty_software` refactored to take a names list (now
  shared by `init` + `provision`). zsh `_ivm` + bash `ivm.bash`: `provision`
  subcommand + unit-name completion via `_ivm_unit_names` (python3 reads the two
  registry JSON keys from `$IVM_ROOT`, heredoc). Verified: `mypy --strict` 0,
  py_compile, `ivm provision --help`, dry-run (classify + unknown-dies), 5 unit
  checks (distro+thirdparty script / thirdparty-only / unknown dies), `bash -n` +
  `zsh -n`, and `_ivm_unit_names` actually emitting `basic_tools claude codex ...`.
  NOT run against real incus (host only).

- [ ] **Phase 2: make `ivm provision emacs` also drop the emacs config files** -
  installing emacs usefully = the `emacs` PACKAGE + your `~/.emacs.d` config files.
  Today `ivm provision <name>` knows only two kinds of name: a package group
  (`roles/distro_packages`) or an install script (`roles/thirdparty_software`).
  emacs needs a third - a set of CONFIG FILES - and one name (`emacs`) has to mean
  "package + config files" together. Work:
  1. Stage the emacs config files on their own, stored ONCE: the `.el` files are
     the same on every distro, so do NOT copy them per-distro like the shell
     dotfiles (those only split per-distro for the `apt-min`/`zypper-min` line in
     `.zshrc`). Put them somewhere like `<ivm-root>/config-files/emacs/`.
     `roles/emacs` already has a "deploy the config" task
     (`deploy-emacs-config.yml`), same shape as zsh's, so it plugs into staging.
  2. Teach `ivm` to push ONE named set of config files into a running VM. Today it
     only pushes ALL the dotfiles, once, at `init` - there is no "push just the
     emacs files later".
  3. A small list file: a name -> the packages and config-file sets it pulls in, so
     `ivm provision emacs` knows what `emacs` means. e.g.:

     ```yaml
     emacs: { packages: [emacs], config_files: [emacs] }   # package + ~/.emacs.d
     qtdev: { packages: [cpp_dev, qt_dev] }                # just two package groups
     ```

     (Maybe later: a name standing for several names, e.g. `devbox` = qtdev + emacs
     + claude.) This finally uses the template's `dotfiles:` field, which `ivm`
     ignores today.
  Exact file + field names: decide when building, don't invent now. Bigger than
  1a/1b because it changes how dotfiles are staged + adds a push-one-set step.

- [ ] **`cpp_dev` + `qt_dev` distro bundles** - the `qtdev` item under "ivm
  real-run fixes + desktop UX" becomes two `distro_packages` bundles (Qt6 + C++
  toolchain, per-family names TO VERIFY on a real box). Then `ivm provision
  cpp_dev qt_dev` (phase 1, raw bundles) or `ivm provision qtdev` (phase 2 group).

- context: **no-ansible-in-guest / no-ssh is intentional.** Running full ansible
  against the VM without ssh would need `community.general.incus` (the incus
  connection plugin) - BANNED here (ansible-core-only, CLAUDE.md). `ivm` IS the
  sanctioned no-ssh path: host-driven `incus exec` + ansible-defined data
  materialized to JSON. `provision` reuses those registries; nothing runs ansible
  in the guest.

## rename `local_pkgs` -> `centralize_lang_pkgs_dir` (planned)

The name is unclear (the author forgot what it did a week after writing it). The
role does NOT install/manage language packages - it REDIRECTS where npm / pip /
pipx / cargo / go put their GLOBAL installs (sets prefixes/env), out of `~/.local/`
into a dedicated tree. So `lang_pkg_managers` would be MISLEADING (implies it
manages packages). Decided: role -> `centralize_lang_pkgs_dir`, dir
`~/.local-pkgs` -> `~/.centralized-lang-pkgs`. Clean sweep, no debt left.

- [ ] **Rename role + dir + toggle + env file + vars** - full blast radius
  (verified: NO apparmor rule, NO Makefile, NO CLAUDE.md refs - the apparmor
  mention in the role README is future-rationale only, not a live rule):

  | # | File | Change |
  |---|------|--------|
  | 1 | `roles/local_pkgs/` | `git mv` -> `roles/centralize_lang_pkgs_dir/` |
  | 2 | `group_vars/all.yml` | `setup_local_pkgs` -> `setup_centralize_lang_pkgs_dir` + comment |
  | 3 | `playbooks/user.yml` | role ref + comment |
  | 4 | `roles/dotfiles/templates/.bashrc.j2` | source-line path + comment |
  | 5 | `roles/zsh/templates/.zshrc.j2` | source-line path + comment |
  | 6 | top-level `README.md` | role-table row |
  | 7 | role `README.md` | full (paths/name/dir) |
  | 8 | role `defaults/main.yml` | toggle name |
  | 9 | role `files/{local-pkgs.env.sh,pip.conf}` + `tasks/main.yml` | dir `~/.centralized-lang-pkgs`, env file -> `centralized-lang-pkgs.env.sh`, vars `_LOCAL_PKGS`/`LOCAL_PKGS_ENV_LOADED` -> matching |

  Independent of the `ivm provision` work; can land anytime. Existing installs
  under the old `~/.local-pkgs/` are left for the user to `rm -rf` (or a one-time
  note in the role README).

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
