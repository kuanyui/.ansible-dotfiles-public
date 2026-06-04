# TODO

Durable mirror of the in-session task list (the task tool is local/ephemeral;
this file is the git-tracked, cross-machine source of truth). Keep in sync.

Status: `[ ]` pending · `[~]` in progress · `[x]` done · `[blocked: #N]`

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
- [ ] **Phase 2 lifecycle + provision depth** - start/stop/delete/overwrite-
  dotfiles/update/env; `post_install_script` (root, `su - user`);
  `distro_package_groups` resolution; openSUSE/Fedora provisioning (distro ->
  pkg-mgr). NOTE: until this lands, only Debian guests are buildable.
- [ ] **Phase 3 extras** - shadow mounts, `sys.tmpfs`, `ssh_server`, `hw.gpu`
  virtio, `net` macvlan/bridge, snapshot CLI, gui (SPICE), parent-dir prompt,
  two-level completion.
- [ ] **Phase 4 retire `incus_agents`** - migrate claude/codex to `ivm`; remove
  the old bash launchers. **Same step:** fold the now-single-consumer shared
  roles into `incus_vm` (`_incus_host_setup` -> `tasks/host_setup.yml`,
  `_incus_guest_setup_dotfiles` -> `tasks/`), and replace
  `make incus-overwrite-dotfiles-in-all-guest` with `ivm overwrite-dotfiles`.
  (Skip the fold-in only if a new incus face role is planned that re-shares them.)
- [ ] **Stale docs** - `roles/incus_vm/README.md` + `make apply/unapply-incus-vm`
  help text still describe the OLD `v-<workstation>` launcher / manifest; rewrite
  for the `ivm` engine.

## Notes / future

- Python launcher rewrite: deferred to the `incus_vm` redesign (see
  `roles/incus_vm/REDESIGN.md`). Trigger = presets / multi-distro /
  Windows. The 11 duplicated subcommands across the two launchers get unified
  there.
- Runtime-unverifiable here (no incus in this env): the `root -> /` push landing
  at `/root`, and `incus list/config get` filtering. Logic is sound; confirm on
  a real incus host.
