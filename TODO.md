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

## Notes / future

- Python launcher rewrite: deferred to the `incus_vm` redesign (see
  `roles/incus_vm/REDESIGN.md`). Trigger = presets / multi-distro /
  Windows. The 11 duplicated subcommands across the two launchers get unified
  there.
- Runtime-unverifiable here (no incus in this env): the `root -> /` push landing
  at `/root`, and `incus list/config get` filtering. Logic is sound; confirm on
  a real incus host.
