# TODO

Durable mirror of the in-session task list (the task tool is local/ephemeral;
this file is the git-tracked, cross-machine source of truth). Keep in sync.

Status: `[ ]` pending · `[~]` in progress · `[x]` done · `[blocked: #N]`

## Handy (offline speech-to-text) - host install + AppArmor complain draft

- [x] `roles/handy` face role (`make apply-handy` / `check-handy`, playbook `handy.yml`): pinned
  v0.9.8 GitHub release asset per family (`.rpm` openSUSE / `.deb` Debian, sha256-checked),
  installed through zypper / apt-get so the declared deps resolve; idempotent on the package
  manager's installed version; typing helpers `xdotool` + `wtype` (+ `ydotool` on openSUSE)
- [x] `roles/apparmor`: `local_pathbased_handy` (template + `tasks/handy.yml` + shadow list +
  `own_flags_mode` registration + sandbox post-check) - COMPLAIN draft authored from source
- [ ] complain pass on the real machine, then promote to enforce - checklist in
  `roles/apparmor/TODO.md`
- [ ] KDE Wayland typing: ydotool daemon + `/dev/uinput` group (manual, see `roles/handy/README.md`)
- [ ] Handy from source on OBS: spec builds offline (prototype in `REFS/handy-obs/`, local;
  findings in `roles/handy/README.md`); next: packaging repo on GitHub + `home:<user>:handy` on
  OBS, run the Action once, then switch `roles/handy` to the OBS repo

## ivm info Usage group (post-init how-to, no more forgetting `llm-key`)

- [x] template schema: optional `usage:` (list of short strings) - the post-init
  how-to `init` printed once and was then lost (set an API key, default account,
  where backups land)
- [x] `ivm info`: Basic gains a `template` row (`user.ivm_template`, placeholder when
  untagged); new final Usage group reads `usage:` LIVE from `<root>/templates/<name>.yaml`
  (template edits update existing VMs' info); placeholders for no-tag / file-gone /
  no-usage - the group always prints
- [x] `llm_librechat` / `llm_openwebui` / `llm_sillytavern` declare `usage:` (web UI +
  account, OpenRouter key via `llm-key` or the web UI, `llm-backup` + backup dir);
  SPEC.md `info` row + template-field table updated

## push-dotfiles fleet safety + template default shell dir

- [x] `make vm-incus-push-dotfiles` pushes to RUNNING VMs only - it used to
  `ensure_up` (boot) every stopped managed VM, which once OOM'd the host (forced
  reboot). Skipped VMs are listed with the exact per-VM command (no silent omission)
- [x] `shell_default_dir_after_login` is now `sh_expand`ed at init like a mount's
  `guest` value, so templates can default it to the mounted project; `codex.yaml` +
  `claude.yaml` (the two `$(pwd)`-mounting templates) set
  `/workspaces/$(basename "$(pwd)")` - `ivm sh` lands in the project without a manual
  `ivm set shell-dir`

## guests follow centralize_lang_pkgs_dir (one install-redirect everywhere)

- [x] rename executed first (see the "rename `local_pkgs` -> `centralize_lang_pkgs_dir`"
  section below) so this extension never references a name scheduled to die
- [x] stage the role's output as dotfiles feature `centralize-lang-pkgs-dir`
  (`stage_dotfiles.yml` include_role, `__common__`/user only) + add it to `ivm`'s
  `BASELINE_DOTFILE_FEATURES` - every guest rc already had the guarded source line
- [x] `init`: inline the STAGED env file into the provision script right after `user`
  exists (`centralized_lang_pkgs_env_provision`; the baseline dotfiles push runs only
  AFTER recipes, on purpose); `provision`: re-push the feature before thirdparty recipes
- [x] recipes source the env file (convention: every npm/pip/pipx/cargo/go recipe does):
  `agent_codex` -> `~/.centralized-lang-pkgs/npm/bin/codex` (fixes: old
  `~/.local/npm_global/bin` was on NO PATH in the guest, `codex` unfindable; no more
  `~/.npmrc` prefix write), `dev_rust` -> `~/.centralized-lang-pkgs/cargo/bin/cargo`
- [x] nvm clash resolved as policy, not workaround: templated rc `unset`s
  `NPM_CONFIG_PREFIX` right before loading nvm.sh (`nvm_die_on_prefix` refuses foreign
  prefixes; where nvm is installed it OWNS npm). `dev_nvm` comment updated
- [x] pvm too (same recipes, same ordering problem): build script writes the staged
  env file right after `user` exists (before recipes); `IMAGE_ENV_PATH` (baked ENV for
  rc-less `podman exec`) swaps `~/.local/npm_global/bin` for the
  `~/.centralized-lang-pkgs/{go,cargo,pipx,pip,npm}/bin` prepends; feature added to the
  template schema enum/default + both templates' `dotfiles` lists (pip.conf parity).
  Image content hash covers the script, so existing images auto-rebuild on next use
- [x] docs: vm_incus SPEC.md (env-file-precedes-recipes contract) + README.md,
  role README ("ivm guests: baseline"), stage_dotfiles.yml header
- [ ] one-time migration of EXISTING VMs (fleet mechanism already existed -
  `make vm-incus-push-dotfiles` loops `ivm overwrite-dotfiles` over managed VMs;
  nothing migration-specific was added to any role). RUNNING VMs only - stopped
  ones are skipped and listed (start each + push individually when you next use
  it; a fleet-wide boot once OOM'd the host):

  ```
  make vm-incus-install
  make vm-incus-push-dotfiles
  ```

  then per VM that had codex (reinstall into the new tree, drop the old one):

  ```
  ivm --name <vm> provision agent_codex
  incus exec <vm> -- su - user -c 'rm -rf ~/.local/npm_global'
  ```

## ivm: trailing `<vm>` name on no-positional subcommands

- [x] no-positional VM-acting subcommands (shell*/start/stop/reboot/delete/update/
  overwrite-dotfiles/gui/info/resize) accept a trailing `<vm>` as a shortcut for `--name`
  (`CWD_RESOLVED_WITH_OWN_POSITIONAL` excludes provision/push/mount/snapshot/expose/unexpose)
- [x] precedence: explicit (`--name` or positional) > cwd; `--name` + positional that
  disagree => error (no silent pick)
- [x] completion: reusable `_ivm_vms_with_dir` (ALL VMs, managed show working dir); `--name`
  and the new positionals use it (zsh shows the dir); `cd` stays managed-only; bash names-only
- [x] docs: SPEC.md (VM resolution + 2a header + completion note), README.md, ivm docstring
- [x] verified: py_compile; `--dry-run` parse (positional targets it, cwd fallback, conflict
  errors, resize positional+flags, provision keeps its unit positional, `sh` alias);
  zsh/bash `-n`; helper output (all-vs-managed)

## ivm detach / lifecycle safety prompts

- [x] `ivm mount detach`: print what it will unbind (`device: host-source -> guest-path`,
  incl. dragged shadow masks) + confirm (`--yes` skips); threaded `assume_yes` through
  `cmd_mount` -> `cmd_mount_detach`
- [x] `stop`/`reboot`/`delete`: loudly warn of live guest interactive sessions
  (`guest_interactive_sessions` via `ps -eo tty=`, deduped per pty) BEFORE the confirm prompt
- [x] docs synced: SPEC.md, README.md
- [x] verified: py_compile; fake-incus detach (listing + `-y` removes mount + its shadow;
  shadow-by-masked-path); PTY test (stop warning fires, `n` aborts)

## ivm cd + list table (+ reusable shell-init wrapper)

- [x] `ivm cd [<vm>]`: print a VM's working-dir root (`user.ivm_init_at_dir`) to stdout;
  no-arg lists managed VMs + dirs on stderr. Non-cwd-resolved (like `adopt`).
- [x] `ivm()` shell wrapper (`files/shell-init/ivm.sh`) so `cd` changes the CALLING shell's
  dir (child can't); new REUSABLE `shell-init` glob sourced by zsh + bash rc (mirrors the
  completions glob) - qvm/pvm can reuse it
- [x] `ivm list` rewrite: table of MANAGED VMs (State/Name/Working Directory/IPv4); any arg
  => raw `incus list` passthrough. Reusable `print_table` + `managed_vm_rows` helpers
- [x] completion: `_ivm_managed_vms` (zsh, `name:dir` -> `_describe` left name / right path);
  bash `cd)` names-only; `cd` added to both subcommand lists
- [x] docs synced: SPEC.md, README.md, ivm module docstring
- [x] verified: py_compile; zsh/bash `-n`; fake-incus e2e (list table, cd, comma-dir, no-arg
  list, die on unknown, passthrough); `vm-incus-sandbox` (install + idempotence + round-trip)

## ivm expose / unexpose: LAN port forwards (incus proxy device)

Open a host TCP port to a VM so the LAN can reach a service in it - the lightweight
alternative to building a host bridge (incus proxy device `nat=true`, not nmcli).

- [x] `cmd_expose` / `cmd_unexpose` in `roles/vm_incus/files/ivm`: `expose <port>` or
  `<host>:<guest>` (docker `-p` style); pins the VM's incusbr0 IPv4 (proxy needs a static
  target; pinned to the current lease -> no reboot) then adds an `expose-tcp-<port>` proxy device
- [x] `expose` no-arg = list forwards; `unexpose` no-arg = remove all (confirms); host-port-in-use + dup checks; `--dry-run`
- [x] `unexpose` no-arg = usage + current forwards, removes NOTHING (superseded "remove all" above); `--all`
  removes all (lists them + confirms); dropped the false "live sessions ... will kill" warning (it
  reused stop/reboot's `confirm_action`); zsh completion `_describe`s each port with its forward + `--all`
- [x] `cmd_info` shows a `forwards:` section
- [x] completion: `_ivm` + `ivm.bash` (`unexpose` completes the VM's open host ports)
- [x] verified: py_compile + `--help` + `--dry-run` (parse / range / non-numeric / would-run); bash+zsh completion `-n`
- [x] restricted-project gotcha: `user-<uid>` projects block proxy devices by default
  (`restricted.devices.proxy=block`); expose now rolls back the IP pin on failure + tells
  you to `sudo incus project set user-$(id -u) restricted.devices.proxy=allow` (admin, one-time)
- [x] incus < 7.2 rejects `listen=tcp:0.0.0.0:<port>` on a `nat=true` proxy ("Cannot listen on
  wildcard address ... when in nat mode"; lifted upstream in v7.2.0) and a VM proxy has NO non-NAT
  mode - `expose` now reads the daemon version (`incus info`) and listens on `0.0.0.0` (>= 7.2) or
  the host's default-route IPv4 (older). Failure advice is picked from incus's actual stderr
  instead of always blaming the proxy-device restriction
- [ ] LIVE-TEST on a real host: the 2026-09-02 first live run failed on the wildcard listen
  address (fixed above); re-test that a forward actually reaches the guest
- [x] `vm-incus-install` allows proxy devices in the user project by default
  (`vm_incus_allow_proxy_devices: true`, opt-out for shared hosts) - `incus_host_install.yml`
- [ ] sandbox = `make vm-incus-sandbox` (blocked in this exec env - no podman build; run on a real host)
- [ ] only host<->VM + this one LAN port; "VM as a full LAN host" still needs a bridge

## guest prompt badge: ivm/qvm/pvm prompt prefix (📦 = isolation level)

Prompt prefix flagging "inside a managed guest"; the box-glyph count encodes isolation
strength. All three launchers share ONE dotfiles set, so the mechanism is generic (NOT
ivm-only). Marker `/etc/ansible-managed-guest-type`, contents = launcher id; the shared
PS1 snippet reads it and the host (no marker) is unchanged.

- [x] shared PS1 j2 (`roles/_shared_j2_snippets/templates/{zsh,bash}_ps1_*.j2`): read the
  marker, `case` -> `ivm`|`qvm` = 📦📦📦 (full VM), `pvm` = 📦 (container); reuses the
  existing `[ -f ... ] &&` host-harmless rc idiom
- [x] ivm writes the marker (`ivm`): `provision_script` (init) + `cmd_overwrite_dotfiles`
  (backfills VMs created before this)
- [x] qvm writes the marker (`qvm`): `cmd_provision` always writes it (QGA root script)
- [x] pvm writes the marker (`pvm`): baked into the image by `build_provision_script`
- [x] verified: py_compile x3 + jinja render + bash/zsh execution test (4 cases correct)
- [ ] sandbox: this exec env cannot build the podman image (fails at the apt build step -
  no systemd session / no outbound net, matching the note below) -> run
  `make vm-incus-sandbox` / `vm-podman-sandbox` / `sandbox-essentials-user` on a real host
- [ ] apply to existing guests: re-run `make vm-incus-install` (re-stage dotfiles) then
  `ivm overwrite-dotfiles` (or `make vm-incus-push-dotfiles`); new guests get it automatically

## ivm provision: dev_go / dev_node / dev_gvm / dev_nvm (lang toolchains + version managers)

- [x] `dev_go` distro bundle - the main `go` (Debian `golang-go` / Suse `go` / RedHat `golang`)
- [x] `dev_node` distro bundle - the main `node` (`nodejs` + `npm`)
- [x] `dev_gvm` = distro deps (`bison`/`gcc`/`make`/`binutils` + Debian `bsdextrautils` for `hexdump`) + thirdparty recipe (gvm pinned @`dd652539`, `gvm install -B`; for pinned/old Go e.g. go1.9)
- [x] `dev_nvm` thirdparty recipe (nvm `v0.40.5` + current LTS Node)
- [x] register all 5 keys in `_shared_prebuilt_provision_assets` render dict (distro + thirdparty)
- [x] shell wiring via `.zshrc.j2` / `.bashrc.j2` templates (guarded; survives the dotfiles push that runs AFTER recipes)
- [x] **live-tested on debian 13** (exec env is an incus KVM): go1.9.7 binary downloads + builds + runs OK. Found+fixed via real runs:
  - gvm hard-requires `hexdump` + `gcc` even for `-B` (was missing/excluded) -> added to the `dev_gvm` distro bundle
  - gvm strip-loop `[ -f ] && sed` aborted the provision under ivm's `bash -ec` when the last rc file was absent -> fixed with `if/fi`
  - `dev_nvm` probe `test -s nvm.sh` marked a C-c-interrupted install "done" forever -> fixed: probe `~/.nvm/alias/default` (last step), so partials re-run
- [ ] **`make vm-incus-sandbox`** (host-side wiring) - blocked in THIS env (no rootless-podman: missing passt + no systemd session); run on a real host
- [ ] KNOWN/accepted: gvm `-B` does NOT verify tarball SHA256 (TLS-only, verified in gvm `scripts/install`) - documented in the recipe; user chose gvm over goenv/g knowingly

## incus_vm storage pool: re-run footgun + reboot-disappearance fix

A host set up with `make INCUS_STORAGE_POOL_SOURCE=/data/...img ... incus-install`
lost every VM after a host reboot followed by a second `make incus-install` run
WITHOUT re-passing the original `INCUS_STORAGE_POOL_*`. Two root causes in
`roles/incus_vm/tasks/incus_host_install.yml` (data was never destroyed - the `.img`
was just unmounted / shadowed):

- [x] **Re-run footgun** - the btrfs loop-file BUILD (truncate/mkfs/fstab/mount) ran on
  every apply, keyed only on the vars passed THAT run. A no-var re-run fell back to the
  DEFAULT source, built a 2nd empty `.img`, and (the fstab line is keyed on the shared
  mountpoint) silently repointed `/var/lib/incus-storage` at it, shadowing the real
  pool. Fix: probe init state EARLY; gate the build on new `_incus_pool_needs_build`
  (= config-wants-loop AND no `default` pool yet) so the build is strictly first-time.
  `_incus_pool_build_loop` kept as the config-derived fact for `storage-info.json`.
- [x] **Reboot disappearance** - the fstab loop entry uses `nofail`, which per
  systemd.mount(5) drops the mount's ordering before local-fs.target, so incus.service
  could start before the loop was mounted and see an EMPTY pool dir. Fix: an
  `incus.service` drop-in `RequiresMountsFor=<mountpoint>` (gated on the pool's REAL
  source == mountpoint, read post-init) + daemon-reload; removed on teardown and when
  the pool is not a loop pool. Verified RequiresMountsFor / nofail semantics vs man7.org.
- [x] **Makefile -> role consolidation** - the `incus-install` recipe was a 21-line inline
  shell blob that `sed`-scraped the role's defaults YAML, validated the driver, probed
  `incus storage list` (a 2nd source of truth next to the role), and `read` a confirm.
  Moved all of it into `tasks/incus_host_install.yml`: driver/size -> `assert`s (fail
  fast), layout preview -> `debug`, confirm -> `pause` (first-time only; gated on
  `ansible_check_mode` + new `incus_install_assume_yes`, mirroring the teardown confirm).
  Makefile recipe is now a one-line `ansible-playbook` call. Behavior change: the confirm
  now runs DURING the play (after the become-pass prompt) and gates the storage commitment
  specifically, not the whole run; dropped the `[override]`/`[default]` origin labels
  (ansible can't tell a `-e` from a default cleanly).
- [ ] **Validate on a real host** - no ansible in the edit env, and `make incus-sandbox`
  skips host setup (`incus_vm_skip_host_setup`), so neither exercises this path. Test:
  first-time `make incus-install`, reboot, re-run no-var `make incus-install`, reboot;
  confirm pool + VMs survive and `/etc/systemd/system/incus.service.d/10-wait-for-pool-storage-mount.conf` exists.
- [x] **Re-runs now FOLLOW the established storage record (a no-var re-run no longer
  pollutes `storage-info.json`)** - resolves the optional item below. The DECISION lives in
  the script, not Jinja: a new READ-ONLY `incus_storage_pool.py resolve` subcommand
  (`resolve_layout` + `cmd_resolve`) reads the recorded `storage-info.json` and prints the
  effective layout as JSON. Rule: once a `default` pool exists WITH a usable record it FOLLOWS
  that record (the layout the pool was built with) and ignores the passed/default vars;
  otherwise (first install / no record) it derives from the request. `incus_host_install.yml`
  calls it ONCE -> `_storage`, which now feeds the build-loop / init / verify / record / boot
  drop-in tasks; this DELETED the scattered `_incus_pool_source_stat` + `_incus_pool_build_loop`
  + `_incus_effective_pool_source/size` `set_fact` chain (net LESS ansible, per the Phase-2
  "logic in the script" direction the first attempt regressed against - caught by the user).
  ivm_install.yml's record write is now just `_storage.record | to_nice_json` -> on a re-run it
  is the EXISTING record echoed back (byte-identical write, no false `MISMATCH`, no wrong `.img`
  in `ivm info`). Two guards on the FOLLOW path (the user's choices): (Q1) overrides passed ->
  loud WARNING carried in `_storage.warnings` (kept, not failed; the no-record driver-mismatch
  FAIL is gated `not _storage.following`); (Q2) the recorded loop `.img` has vanished -> resolve
  exits non-zero so the `script` task FAILS with a remount-first / teardown banner, never
  silently rebuilding empty storage. `resolve` runs `check_mode: false` (read-only) so `make
  incus-check` still gets `_storage`. Verified: py_compile; 5 `resolve_layout`/`cmd_resolve`
  unit tests (reconcile-follow reproduces the record byte-for-byte; first-time derive; Q2
  exit-2; Q1 warning in JSON; dir backend); `ansible-playbook --syntax-check`; localhost e2e
  driving the real script (reconcile-with-defaults follows record + needs_build=false;
  first-time build-loop/init args; Q2 rc=2). Real-host validation still pending.
- [x] **`storage-status` now decodes the "why is the same `.img` mounted so many times"
  picture** - `incus_storage_pool.py status` gained a final "how it is mounted" section: a
  plain chain (`.img` -> loop device -> btrfs mount -> incus BIND mount -> per-VM subvolume
  `root.img`) + a decode of every `/proc/mounts` line backed by the loop `.img` (matched by
  RESOLVED backing file, so it works whether `/proc/mounts` shows `/dev/loopN` or the
  libmount-style `.img` path), each labelled (loop mount / incus bind / running instance:
  <subvol>). Answers the user's "is my `/data/vm/incus-btrfs.img` actually used, and is the
  32GiB `root.img` eating `/`?" (no - `storage-pools/default` is a bind mount; the blocks live
  in the `.img`). Skipped for non-loop layouts (`dir`). Verified: py_compile + render
  simulation against the user's REAL `mount` output (matches the 3 loop-backed mounts;
  excludes the nvme system subvols, the `cr_home` virtiofs binds, `/data/vm` ext4, tmpfs).
- [ ] (optional, SUPERSEDED by the follow-record item above) `storage-info.json` still
  records the CONFIG source, so `ivm info` can show a wrong `.img` path after a no-var re-run;
  feed `_incus_pool_real_source` instead. Keep until real-host-validated, then drop.
- [ ] (note, pre-existing) `make incus-check` skips command-probes in check mode, so the
  dry-run can error on probe-result `when:`s - out of scope for this fix.
- [x] **Ghost mount survives teardown -> a changed source never takes effect** (the
  week-long footgun on host `<the-real-host>`). `make incus-teardown-host` deleted the
  `default` pool but NEVER unmounted `/var/lib/incus-storage` nor removed its fstab line,
  so the loop device kept the old `/home/incus-storage.img` open as a `(deleted)` ghost
  mount across teardown+reinstall cycles. The install mount task was keyed on
  `mountpoint -q` ALONE (not the backing source), so it reported ALREADY_MOUNTED over the
  ghost and the new `/data/vm/incus-btrfs.img` never mounted (stuck at 4.65MiB; pool not
  on it). Fixes: (a) `incus_host_uninstall.yml` under `delete_default_storage_pool` now
  `umount`s the loop mountpoint + removes its fstab line (the `.img` is left for reuse);
  (b) the install mount task (`incus_host_install.yml`) resolves the mounted backing file
  (`findmnt`+`losetup`, strips ` (deleted)`) and REMOUNTS from the wanted source when it
  differs (safe: runs only when no `default` pool exists). Verified: ivm py_compile,
  no-tab YAML, `make -n` flag expansion.
- [x] **Silent `dir` despite an explicit `INCUS_STORAGE_POOL_*` override** - a pre-existing
  hand-made `dir` `default` pool makes preseed skip, so the override had ZERO effect and
  the only signal was a `debug:` warning buried in `--diff`. Now the Makefile passes
  `incus_storage_pool_overrides_passed=true` when any `INCUS_STORAGE_POOL_*` is set (new
  `_pool_any_set`); the role hard-FAILS (not warns) on a driver mismatch when that flag is
  set, printing the exact `make incus-teardown-host && make incus-install ...` rebuild
  command; reconcile runs (no override) keep the soft `debug`. Also the REQUESTED layout
  preview is now ALWAYS printed (was first-time-only) - addresses "playbook didn't show me
  the settings". New default `incus_storage_pool_overrides_passed: false`.
- [x] **`ivm` preview box self-contradiction** - it printed the LIVE pool driver
  (`default (dir)`) on top and the RECORDED btrfs loop line below as if consistent.
  `storage_location_lines` now compares recorded vs live driver and prints a
  `⚠ MISMATCH ...` block (with the teardown+reinstall hint) instead of the false loop line.
  (Covers the driver-mismatch variant of the optional `storage-info.json` item above.)
- [ ] **Validate the above on a real host** (same env limit: no ansible/incus here).
  Recovery to verify on `<the-real-host>`: `make incus-teardown-host` (now unmounts the
  ghost + clears fstab), then `make incus-install INCUS_STORAGE_POOL_SOURCE=/data/vm/incus-btrfs.img INCUS_STORAGE_POOL_SIZE=100GiB`;
  confirm `incus storage list` shows `default | btrfs` and `ivm init` lands the disk under
  `/var/lib/incus-storage` (-> `/data/vm/incus-btrfs.img`), not the `dir` tree on `/`.
- [x] **Extract storage inspection/verification to `files/incus_storage_pool.py` (Phase 1
  of "stop cramming storage logic into unreadable ansible")** - new READ-ONLY standalone
  script (stdlib only). `status` = full live picture (`incus storage list`, default pool
  driver/source, loop-file footprint, mount + its backing file, /etc/fstab line, recorded
  storage-info.json, + a consistent / MISMATCH / no-pool verdict); `verify
  --expect-driver/--expect-source/--expect-loop-backing` = non-zero exit on mismatch.
  Wired: (a) `incus_host_install.yml` END prints `status` + (first-time only) runs `verify`
  via the `script` module -> install self-checks, a silent `dir`/stale-loop result FAILS
  loudly; (b) `ivm storage-status [--json]` runs the same script (installed to
  `incus_vm_ivm_dir`) -> one command for the whole storage picture; (c) zsh + bash
  completions. Verified: py_compile, verdict() unit-tested (driver-mismatch / ghost-mount /
  consistent / not-mounted), `ivm storage-status --help` + dispatch, `bash -n`,
  `ansible.builtin.script` `cmd:` + role `files/` resolution confirmed vs ansible docs.
- [x] **Phase 2: folded the MUTATING build-loop / init / delete-pool logic into
  `incus_storage_pool.py`** (subcommands `build-loop`, `init`, `delete-pool`; each prints
  argv before acting, is idempotent, ends with `RESULT: changed|noop`; `__main__` catches
  CalledProcessError -> clean error, no traceback). ansible now CALLS them via the `script`
  module: `incus_host_install.yml` lost the 6 truncate/blkid/mkfs/mkdir/fstab/mount tasks
  (-> one `build-loop`) and the `incus admin init` task (-> one `init`); `incus_host_uninstall.yml`
  lost the pool-delete + umount + fstab tasks (-> one `delete-pool`). `init` renders the
  preseed (pool + incusbr0 + default profile) in Python (`build_preseed`, fed as JSON =
  valid YAML), so `templates/incus_preseed.yml.j2` was DELETED (refs updated). TESTED against
  REAL incus 6.0.4 + real loop/btrfs in this Debian-13 guest (installed incus + btrfs-progs +
  dnsmasq-base + ansible-core via apt): (1) direct script run - 25 assertions incl. full
  build->init->verify->delete cycle, ghost-mount eviction, idempotency (noop on re-run),
  negative verify; (2) end-to-end `ansible-playbook` driving the role's `script`-module tasks
  -> build-loop/init/verify/delete-pool all `changed`/`ok`, `failed=0`, pool/mount/fstab clean
  after. Both playbooks `--syntax-check` clean. (NOTE: the incus.service `RequiresMountsFor`
  boot-mount drop-in stays in ansible - it is post-init + reconcile-driven, not the messy part.)
- [ ] **(separate, optional) split the 2076-line `files/ivm` monolith into a package.** Asked
  by user ("ivm 還不需要分檔嗎"). The storage concern is now OUT of ivm's orbit (this script).
  A full ivm split is a distinct effort with a DEPLOYMENT tradeoff (today: one self-contained
  file = one `copy`; a package needs either a thin `~/.local/bin/ivm` launcher that `exec`s
  `python3 -m <pkg>` over a shipped module dir, or a zipapp build step). Recommend the
  thin-launcher + module-dir approach, as its OWN pass, after the storage work is confirmed on
  the real host. NOT done here. (ivm's own `cmd_info` storage helpers still duplicate the
  script's status rendering at a per-VM scope - candidate to delegate later.)

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
  (`roles/fcitx5_quick_phrase` is Quick Phrase files ONLY - not the place for this.)
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
- [x] **Light-desktop apps on icewm** - RESOLVED via a dedicated `distro_packages_lxqt_desktop`
  bundle (full LXQt: lxqt-session/panel + openbox + `pcmanfm-qt` file manager + `qterminal`,
  autologin like icewm_desktop) instead of bolting apps onto icewm or forking a `desktop`
  template - `ivm provision gui_x11 lxqt_desktop`. icewm_desktop itself also gained a terminal
  (`lxterminal`, bound to Ctrl+Alt+T) so the bare-WM desktop is usable too. Still optional:
  `lximage-qt` image viewer (add to either bundle if wanted; GTK `gpicview` is abandoned).
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

- [x] **`ivm adopt` + `user.*` tag rename** - older-ivm / hand-made VMs carry no
  `user.ivm_init_at_dir`, so the cwd resolver (and thus `ivm info`) can't find
  them. Added `ivm --name <vm> adopt`: forces `--name` (never resolves by cwd -
  the binding is what it creates), interactively (re)writes the canonical tags
  (prefill = current value, blank skips, enum fields validated), and unsets the
  legacy hyphenated keys. Also standardized the tag separator on `_` (incus
  `user.*` is free-form, no convention - these are ivm's own keys, so be
  internally consistent): `user.ansible-managed` -> `user.ansible_managed`,
  `user.ansible-guest-os` -> `user.ivm_guest_os` (the latter also gains the `ivm_`
  prefix; `ansible_managed` keeps its name as the host-wide ownership flag). The
  three pre-existing `user.ivm_*` keys were already `_`. Updated the two
  Makefile readers (`incus-push-dotfiles`), both completions, the module
  docstring. Verified: `py_compile`, `bash -n`/`zsh -n`, `make -n`, and dry-run
  smoke (write commands, missing-`--name` error, enum re-prompt). NOT run against
  real incus.

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
opt-in via its own `make apply-firefox-tunes` target (no `user.yml` wiring, no gate).

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
- [x] **Wiring + verification** - `playbooks/firefox_tunes.yml` +
  `make apply-firefox-tunes` / `check-firefox-tunes` (+ `.PHONY`,
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

- [x] **Phase 2: make `ivm provision emacs` also drop the emacs config files** -
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
  **DONE:** `distro_packages_emacs:{common:[emacs]}` bundle; `ivm_install.yml`
  stages the emacs config ONCE (not per-family) into `config-files/emacs/.emacs.d/`
  via `roles/emacs deploy-emacs-config.yml` (user, is_root=false) + adds `emacs` to
  the rendered `distro-package-groups.json`. `ivm`: `config_sets_dir` +
  `push_config_set_commands` (`incus file push --recursive --uid 1000` each
  top-level entry -> /home/user, mirrors push_dotfiles); `cmd_provision` rewritten
  to MULTI-MATCH - a name applies as a distro bundle AND/OR thirdparty recipe AND/OR
  config set, so `emacs` = install the `emacs` package + push `~/.emacs.d`; unknown
  lists all three. zsh+bash completion lists config-set names too (deduped - `emacs`
  is in two registries). DESIGN decided: `config-files/<set>/` FOLDERS are the list
  (no new JSON registry); "one name = package + config" = the same name in two
  registries (multi-match), no separate mapping file. Verified: `mypy --strict` 0,
  py_compile, `bash -n`/`zsh -n`; REAL `ansible-playbook` staged
  `config-files/emacs/.emacs.d/{init.el,lisps}` (single copy); the REAL INSTALLED
  `ivm provision --dry-run` against the REAL registries multi-matched
  `emacs`->bundle+config-set, `basic_tools`->bundle, `claude`->thirdparty, and
  unknown-dies-listing-all-3. NOT verified: incus-runtime push into a live VM +
  apt-install emacs - this host's unprivileged `user-1000` project has no IPv4 (the
  documented net gap; host setup aborted at the group-activation gate) and the image
  server hung, so no container/VM could boot here. The push is a thin `incus file
  push` wrapper; the distro-install path is unchanged from 1b. NOT wired: `ivm init`
  from a template's `dotfiles:` field still ignores config sets (provision is the
  path; that field stays unused - a follow-up if init-time emacs config is wanted).

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

## rename `local_pkgs` -> `centralize_lang_pkgs_dir` (DONE)

The name is unclear (the author forgot what it did a week after writing it). The
role does NOT install/manage language packages - it REDIRECTS where npm / pip /
pipx / cargo / go put their GLOBAL installs (sets prefixes/env), out of `~/.local/`
into a dedicated tree. So `lang_pkg_managers` would be MISLEADING (implies it
manages packages). Decided: role -> `centralize_lang_pkgs_dir`, dir
`~/.local-pkgs` -> `~/.centralized-lang-pkgs`. Clean sweep, no debt left.

- [x] **Rename role + dir + env file + vars** - DONE. The original table here
  predated the interim `local_pkgs` -> `local_lang_pkg_managers` rename, so its
  `group_vars` toggle / `roles/dotfiles/` rows were stale (neither existed);
  actual blast radius as executed:

  | # | File | Change |
  |---|------|--------|
  | 1 | `roles/local_lang_pkg_managers/` | `git mv` -> `roles/centralize_lang_pkgs_dir/` |
  | 2 | `playbooks/local_lang_pkg_managers.yml` | `git mv` -> `playbooks/centralize_lang_pkgs_dir.yml`, play name + role ref |
  | 3 | `playbooks/user.yml` | comment mention |
  | 4 | `Makefile` | target `apply-local-lang-pkg-managers` -> `apply-centralize-lang-pkgs-dir` (+ `.PHONY`, help text) |
  | 5 | `roles/bash/templates/.bashrc.j2` | source-line path + comment |
  | 6 | `roles/zsh/templates/.zshrc.j2` | source-line path + comment |
  | 7 | top-level `README.md` | playbook-tree line + role-table row |
  | 8 | role `README.md` | full (paths/name/dir; also fixed the stale `setup_*`-toggle opt-in section - no toggle exists, opt-in is the dedicated playbook) |
  | 9 | role `files/{centralized-lang-pkgs.env.sh,pip.conf}` + `tasks/main.yml` | dir `~/.centralized-lang-pkgs`, env file `local-lang-pkg-managers.env.sh` -> `centralized-lang-pkgs.env.sh`, guard vars `_CENTRALIZED_LANG_PKGS` / `CENTRALIZED_LANG_PKGS_ENV_LOADED` |

  (`REFACTOR.md` mentions the old names as history of the earlier rename - left
  as-is on purpose.)

- [ ] One-time migration on each host that had the role applied (the layout
  inside the tree is unchanged, so a rename IS the whole migration):

  ```
  mv ~/.local-lang-pkg-managers ~/.centralized-lang-pkgs
  rm ~/.centralized-lang-pkgs/local-lang-pkg-managers.env.sh
  make apply-centralize-lang-pkgs-dir
  make apply-essentials-user
  ```

  (`rm`: the old-name env file rode along in the `mv`; the new one is deployed
  by the make target. `apply-essentials-user`: re-renders `~/.zshrc`/`~/.bashrc`
  so their guarded source line points at the new path.)

## profile_tasks callback: boot-style run/skip log

- [x] **`callback_plugins/profile_tasks.py`: print every task in execution order
  with a systemd-boot-style status tag BEFORE the timing summary** - `[  OK  ]`
  ran, `[ SKIP ]` skipped (e.g. `when:` false), `[ FAIL ]` failed/unreachable;
  then the existing top-N timing table. One record per task captured at
  `v2_playbook_on_task_start` (so the list is in execution order), upgraded by
  `v2_runner_on_ok/skipped/failed/unreachable` with precedence fail>ok>skip
  (ok-on-host1 + skip-on-host2 stays OK; any failure wins). OK=green, FAIL=red,
  SKIP=default colour (via `display(..., color=)`, which respects ansible's colour
  settings). Verified: a real `ansible-playbook` run (ok / `when:false` skip /
  changed / loop / `when:1>2` skip - all tagged correctly, in order) AND the real
  120-task `incus_vm.yml` apply.

## ivm dev toolchain provision groups (dev_qt / dev_rust / dev_android)

Added `provision` units for basic dev: `dev_qt` (distro: Qt6 Core/Gui/Widgets/Concurrent
+ multimedia + QML + Linguist + cmake/make/compiler), `dev_rust` (thirdparty: rustup +
rust-analyzer), `dev_android` (distro JDK+unzip + thirdparty: Android SDK cmdline-tools ->
sdkmanager platform-tools/build-tools/platform). Kotlin needs nothing extra - Android Gradle
pulls the Kotlin compiler per project.

- [x] `dev_qt` / `dev_android` distro groups (`roles/distro_packages/defaults/main.yml`),
  rendered into `distro-package-groups.json` + wired into the host `distro_packages_install_*`
  toggle loop (`tasks/main.yml`) + `group_vars/all.yml` (both default `false`, opt-in).
- [x] `dev_rust` / `dev_android` thirdparty recipes (`roles/thirdparty_software/defaults/main.yml`),
  rendered into `thirdparty-software.json`. Package names verified against upstream DBs / docs.
- [ ] **Host runner for thirdparty recipes** - `roles/thirdparty_software` is defaults-only
  (no `tasks/`); only `ivm` (guest) executes recipes. So on the HOST, `dev_rust` (rustup) and
  the `dev_android` SDK half can't be installed via ansible - user runs rustup / sdkmanager by
  hand. A host-side runner (probe-then-`install_script`, mirroring ivm's `thirdparty_install_script`)
  would close the gap. Separate effort.
- [ ] **Validate in a guest** - no incus in this env. `ivm provision dev_qt` / `dev_rust` /
  `dev_android` on a Debian + an openSUSE + a Fedora guest; confirm package names resolve, rustup
  lands in ~/.cargo, sdkmanager builds out ~/Android/Sdk. Bump the pinned cmdline-tools build
  number (14742923) / API 36 if stale.

## distro_packages optional `post_install` + icewm_desktop

`gui_x11` is only the X SERVER stack (by design - WM/DE + display-manager are per-VM). So
`ivm provision gui_x11` on a headless template gives no desktop. To make "add a desktop in
one shot" possible, distro_packages bundles gained an OPTIONAL `post_install` key.

- [x] **Per-family overlay `{install, post_install}`** - each family overlay
  (`common`/`debian`/`suse`/`redhat`) is EITHER a bare package list (usual) OR a dict
  `{install: [...], post_install: <shell>}`, so a family's packages AND its setup stay
  co-located under that family and the bundle's TOP level is purely families (the {DISTRO}
  layer keeps one meaning). Resolution (host + guest): packages = `common`.install +
  `<family>`.install; post_install = `common`.post_install + `<family>`.post_install
  (ADDITIVE). `post_install` runs as root in the guest after the packages, post-user-creation
  (so `su - user` works), idempotent. GUEST-ONLY: host install path runs packages only (it
  assumes bare-list overlays; dict-form bundles stay out of the `distro_packages_install_*`
  loop). `ivm`: `overlay_install_packages` / `overlay_post_install` normalize the union in ONE
  place; `resolve_group` + `group_post_install_snippet` use them; called in `provision_script`
  (init) + `cmd_provision`. Verified vs the real ivm functions: existing bare-list bundles
  unchanged, nested packages = common+family (no post_install leak), per-family post_install
  appends the family extra ONLY on that family, mixed bare+dict overlays in one bundle work;
  `bash -n` ok; host bare-list Jinja still yields only strings.
- [x] **`distro_packages_icewm_desktop`** (nested form) - `common.install` icewm + lightdm +
  spice-vdagent; `common.post_install` wires graphical.target + lightdm autologin (icewm
  session DETECTED per-distro: Debian `icewm-session` / openSUSE `icewm`) + spice-vdagent
  autostart. Per-family `install` carries ONLY the greeter (the one per-distro difference, a
  PACKAGE not a script): Debian/openSUSE `lightdm-gtk-greeter`, Fedora `lightdm-gtk`. Rides on
  `gui_x11`: `ivm provision gui_x11 icewm_desktop`.
  - Greeter bug fix: ivm installs with recommends OFF (apt-min/zypper-min/dnf-min), so the
    greeter is NOT auto-pulled - listed explicitly. Fedora name verified via packages.fedoraproject.org.
- [x] **icewm terminal + Ctrl+Alt+T** - icewm_desktop shipped no terminal and (verified via
  icewm-keys(5)) has NO default terminal hotkey - the man page's `key "Alt+Ctrl+t" xterm` is only
  an example. Added `lxterminal` (common.install; user-chosen lightweight terminal) + a
  `common.post_install` line writing `~/.config/icewm/keys` = `key "Ctrl+Alt+t" lxterminal`, so a
  fresh icewm desktop is usable. lxterminal: same package name on Debian/Fedora/openSUSE.
- [x] **`distro_packages_lxqt_desktop`** - sibling desktop bundle (pick ONE with icewm_desktop):
  a full lightweight Qt DE. `common.install` lxqt-session + lxqt-panel + openbox (LXQt's X11 WM,
  not auto-pulled with weak-deps off) + `pcmanfm-qt` (file manager) + `qterminal` (terminal) +
  lightdm + spice-vdagent; same autologin `common.post_install` (session DETECTED via
  `/usr/share/xsessions/*lxqt*.desktop`). Per-family `install`: greeter (Debian/openSUSE
  `lightdm-gtk-greeter`, Fedora `lightdm-gtk`) + Fedora-only `lxqt-x11-session` (Fedora splits the
  X11 session .desktop into that subpackage). LXQt honors XDG autostart so spice-vdagent
  self-starts - no icewm-style startup hack. Wired into ivm's distro-package-groups.json render +
  auto-completes. Rides on gui_x11: `ivm provision gui_x11 lxqt_desktop`. Per-family names verified
  (Debian lxqt-core deps / openSUSE Portal:LXQt / packages.fedoraproject.org).
- Decision log: started with a sibling `post_install` key (kept overlays mono-typed) but that
  POLLUTED the family layer (post_install sitting beside debian/suse/redhat) and duplicated the
  family enumeration. Switched to the nested per-family `{install, post_install}` (the user's
  original instinct): family layer stays pure, per-family setup is co-located, and the union is
  normalized in one ivm helper (the only real cost, and it is small). Also rejected renaming
  `thirdparty_software` -> `provision_recipes` (breaks the template key for a config-not-install
  case); `thirdparty_software` stays for genuine non-distro installs.
- [ ] **Validate in a guest** - `ivm init` a headless template then
  `ivm provision gui_x11 icewm_desktop`; `ivm gui` shows the icewm desktop (autologin worked,
  session name detected, greeter present so lightdm starts, spice-vdagent gives live resize).
  Debian = primary target; openSUSE mirrors templates/webbrowser.yaml. Also: on icewm verify
  Ctrl+Alt+T opens lxterminal; and `ivm provision gui_x11 lxqt_desktop` brings up an LXQt desktop
  with pcmanfm-qt + qterminal reachable from the panel menu.
- [ ] **Fedora icewm_desktop is best-effort/untested** - SELinux Enforcing has known
  lightdm-autologin issues (.xsession-errors write denials / home context; redhat bugzilla
  1900334, 1323426). Once a fix is verified on a real Fedora box it goes in
  `post_install.redhat` (the per-family slot now exists for exactly this).
- [ ] (note) `templates/webbrowser.yaml` installs bare `lightdm` (no greeter) on openSUSE via
  the same recommends-OFF path - it only works if openSUSE's lightdm HARD-requires a greeter.
  Worth confirming on a real Tumbleweed box; if not, add `lightdm-gtk-greeter` there too.
- [ ] (future, optional) host-side `post_install` / host GUI - currently guest-only; a host
  path would need the real-user (not `user`) convention. Same bucket as the thirdparty
  host-runner above.

## mpv config: migrate dotfiles into ansible (new `mpv` role)

User keeps an mpv config in a separate dotfiles repo, not yet migrated into this
ansible project. The apparmor work this session pinned a HARD requirement that the
migration must carry, so record it before it is lost.

Why it matters (this session): `roles/apparmor/templates/mpv/local_pathbased_mpv.aa.j2`
is the no-GPU (software) profile for plain `mpv`. After `9e942af` gated X11 behind
`apparmor_allow_x11=false`, plain `mpv` on a Wayland session showed NO window but kept
audio and had to be `pkill`ed. Chain: `vo=gpu` (default) probes the X11 context first
(now xauth-denied, silently), falls back to the Wayland context, which opens
`/dev/dri/card1` for GBM and DEADLOCKS at mp_rendezvous (mpv#8506). `card1` was the
visible AVC; the X11 cutoff was the root. Proven by controlled comparison (Tuesday->now
only xauth changed) + `mpv --vo=wlshm` playing fine under the broken profile on Wayland.

- [x] **Create an `mpv` config role (migrate from the separate dotfiles).** DONE:
  `roles/mpv` deploys 6 files to `~/.config/mpv/`. From the legacy stow `mpv/`
  package (source: `REFS/STOW_DOTFILES`, untracked): `mpv.conf` (now `vo=wlshm` +
  rationale comment + `window-dragging=no`; `sub-ass-force-style` renamed to
  `sub-ass-style-overrides` - kills the startup warning), `input.conf`. Plus vendored
  touch-gesture scripts (see swap item below): `scripts/pointer-event.lua`,
  `scripts/touch-gestures.lua`, `script-opts/pointer-event.conf`,
  `script-opts/touch-gestures.conf`.
  (`KDE_global_shortcuts_examples.sh` was migrated then REMOVED at user request -
  reference-only socat snippets, unused; the socat pattern lives on inline in
  `mpv.conf`'s IPC comment.) SANITIZATION DROPS (see `roles/mpv/README.md`): per-machine hostname
  profiles (device fingerprint; HOSTNAME-env mechanism broken on Linux; its
  `input-ipc-server` carried commented-out at top level; its touchscreen fix carried
  as UNCONDITIONAL `window-dragging=no` - touch drag = emulated left-button drag =
  window flies around; KWin title-bar/Meta+drag unaffected, and mpv-gestures requires
  it off anyway), `lib-for-conf.lua` (served
  only those profiles + printed per-launch log noise), the `p` binding (personal helper
  path, macOS-era, dead on Linux). Wired: `playbooks/mpv.yml`, `setup_mpv: false` gate,
  `user.yml` entry, `make apply-mpv`/`check-mpv`, README tree + role table. VERIFIED:
  syntax-check; end-to-end on a throwaway `target_home` (all 6 files land, run2
  `changed=0`); stow-symlink guard refuses with the `stow --delete mpv` hint and writes
  0 files through the link. PENDING on the real host: unstow old `mpv/`, `make
  apply-mpv`, then plain `mpv <file>` must open a window (X11 stays denied). Note:
  `profile=sw-fast` NOT set - wlshm alone proved fine in the user's test; add only if
  high-res playback stutters.
- [x] **touch gestures: swapped the old scripts for christoph-heinrich's** - user found
  the old `mpv-gestures` seek hard to control (absolute position) and SLUGGISH. Root
  cause: it did `seek absolute exact` every drag tick (exact = frame-accurate = slow).
  Surveyed upstream; christoph-heinrich's [`mpv-touch-gestures`] does a fast
  `keyframes` seek WHILE dragging and one `exact` seek when you stop - smooth, and the
  responsive feedback itself cures the overshoot. (Rejected a custom velocity/momentum
  model: momentum overshoots for SEEK - it is literally what the old script's inertia
  did and the user disliked.) Vendored 2 `.lua` (pointer-event 1.2.1 + touch-gestures
  1.1.0) + 2 `.conf`; retired `touchscreen-seek.lua` + `touchscreen-drag-seek.lua`;
  removed the dangling `MBTN_LEFT_DBL script-binding touchscreen-seek` from `input.conf`
  (pointer-event owns the left button via forced binding). Both `.lua` SECURITY-REVIEWED
  (grep + full read): pure mpv API, args numeric/hardcoded verbs, ZERO
  `os/io/subprocess/run/load/socket/package` - safe. Set `horizontal_drag=seek` in
  `touch-gestures.conf` (upstream default is `playlist`); `seek_scale` is the
  overshoot/sensitivity knob (lower = finer). `left_long` -> uosc menu (harmless warning
  if no uosc). `.lua` kept verbatim (track upstream), only `.conf` tuned. FEEL is
  on-device only (no mpv/touchscreen here) - user tests + tunes `seek_scale`.
- [x] **drag-seek velocity acceleration (local patch on touch-gestures.lua)** - user
  noticed christoph's drag-seek is still LINEAR (1:1 drag distance -> time, just smooth).
  No upstream accel hook + no off-the-shelf script does velocity-based seek, so added a
  marked `LOCAL ADDITION` in `drag_seek`: `dx = dx * (|dx|/ref)^(exp-1)` - amplifies fast
  flicks, attenuates slow drags (reach + precision from one gesture). Tunable in
  `touch-gestures.conf`: `seek_accel_exponent` (default 1.5; =1 restores upstream linear),
  `seek_accel_pixels_ref` (default 10, neutral-speed px, guarded > 0). Pure arithmetic on
  the drag delta - no new API, still safe. touch-gestures.lua is now upstream+1-patch (NOT
  verbatim) - README "Drag-seek acceleration" + the `LOCAL ADDITION` comments flag it for
  any future upstream re-sync. FEEL untestable here - user tunes exponent/ref on-device.
- [x] **drag-seek touch-jitter fix (deadzone) + gentler accel defaults** - on-device
  (KDE Wayland default touch): slow drag SHOOK back and forth, fast flicks overshot. Root
  cause: noisy touch `mouse-pos` + a seek on EVERY event + keyframe snapping (and accel
  amplified the noise spikes; `proportional_seek=yes` makes it worse on long videos). Fix
  in `drag_seek`: (1) DEADZONE - accumulate raw px into `seek_pending`, seek only once it
  clears `seek_deadzone_pixels` (default 6); jitter oscillates around 0 and never crosses,
  a steady drag does. Reset in `drag_start`. (2) accel now runs on the cleared chunk, gain
  CLAMPED to `seek_accel_max_gain` (default 4), exponent default lowered 1.5 -> 1.25. New
  conf knobs + README updated, incl. the `proportional_seek=no` tip for long videos. Still
  pure arithmetic (safe). Verified: deploy + idempotent. FEEL still on-device - user dials
  `seek_deadzone_pixels` (jitter) / `seek_accel_exponent` (overshoot).
- [x] **drag-seek: explicit slow-ratio base + amplify-only accel + fast ceiling** - jitter
  was fixed but user wanted (a) a strong fixed reduction when slow ("drag 5cm, bar moves
  1cm" = 5:1) and (b) a fast rate cap. Key realization: with `proportional_seek=yes`,
  `seek_scale` IS the finger:seek-bar ratio, so set `seek_scale=0.2` (5:1) as the slow
  base. Changed the accel to AMPLIFY-ONLY (floor gain at 1, `if gain < 1 then gain = 1`)
  so a slow drag stays exactly at the base ratio and accel only speeds up from there, up
  to the ceiling `seek_scale * seek_accel_max_gain` (0.2 * 5 = 1.0 = fast full-screen swipe
  = whole video). Knobs are now intuitive: `seek_scale` = slow ratio, `seek_accel_max_gain`
  = fast cap. conf default `seek_scale 1 -> 0.2`, `seek_accel_max_gain 4 -> 5`; README model
  section rewritten. Verified deploy + idempotent. On-device: tune `seek_scale` (slow) /
  `seek_accel_max_gain` (fast cap).
- [x] **pause-while-scrubbing** - user: video keeps playing under the finger during a
  drag-seek. Added (touch-gestures.lua): in `drag_init`'s seek branch capture pause state
  + `set pause=true`; restore in `drag_end` (guarded var `seek_paused_by_drag`, nil unless
  a seek scrub is active so volume/speed drags are untouched). Knob
  `seek_pause_while_dragging` (default yes). Restores to the PRIOR state, so a paused video
  stays paused. README + conf updated. Verified deploy + idempotent.
- [x] **positional TAP-zone system** - user wanted a grid: top 25% = speed row
  (left/center/right tap = prev preset / 1.0x / next preset, OSD shows x), rest = seek/pause
  row (l/c/r single = -3s/pause/+3s, double = -10s/fullscreen/+10s), bottom strip = OSC.
  Implemented in touch-gestures.lua: routed `left_single` through the script (was a plain
  `cycle pause`) so BOTH single & double dispatch by `tap_zone()` (reads mouse-pos -> row by
  `top_zone_fraction`, col by thirds). Speed steps a discrete `speed_presets`
  list (`0.25,0.5,1,1.5,2,3,4`, clamped). pointer-event.conf margins -> left/right/top 0
  (full-width thirds + active top), `margin_bottom=130` KEPT (user first asked for 20% then
  reverted to 130, so NO pointer-event.lua fractional-margin patch was needed - it stays
  verbatim). Drags (h-seek / v-speed-volume) untouched & still work everywhere. Pure mpv API
  (safe). Verified deploy + idempotent. NOTE: single-tap inherits mpv's ~300 ms double-tap
  wait (status quo). FEEL on-device - user can tune `top_zone_fraction` / `speed_presets`.
- [ ] **GPU-launcher interaction** - `ansible-mpv-gpu.desktop`'s Exec has no `--vo`, so
  a global `vo=wlshm` makes the GPU launcher run software too (it no longer hangs, but
  gets no hardware). TRUE hardware via the launcher needs a SEPARATE decision: grant
  `local_attachmentless_mpv_gpu` the `/dev/dri/card[0-9]* rw` modesetting node (KWin
  advertises the card node here, not renderD) AND add `--vo=gpu` to the launcher Exec to
  override the wlshm default. Deferred until hardware is actually wanted.
- [x] **apparmor side done this session** - added `deny /dev/dri/card[0-9]* wr,` to
  `local_pathbased_mpv.aa.j2` (silences the card1 audit noise; completes the existing
  renderD/nvidiactl/udmabuf deny block). Uncommitted in the working tree.

## kde_touchscreen_desktop_entries role (built + verified on throwaway env; needs a real-host run)

Migrate the user's touchscreen KDE menu entries from the legacy stow
`xdg-desktop-screen-rotation` package (source: `REFS/STOW_DOTFILES`, untracked) into a new
role. Bundles 3 concerns under ONE role per the user's "one role" request: screen rotation,
screenshots, a display-settings shortcut. Named for the touchscreen use case ("desktop
entries" = the XDG term for `.desktop` files).

- [x] **Create `roles/kde_touchscreen_desktop_entries`.** DONE: deploys 6 `.desktop` files
  to `~/.local/share/applications/` (`ansible_`-prefixed per the repo convention - cf.
  `ansible_telegram`; `ansible_display_*` = 3 rotation entries + 1 systemsettings
  display shortcut, `ansible_take_screenshot_*` = 2 spectacle screenshots that save to
  `$(xdg-user-dir PICTURES)/Screenshots` - resolved at click time, NOT a hardcoded
  `~/Pictures`; the role resolves the same dir at deploy and `mkdir`s it) + the
  `rotate_screen` helper to `~/.local/bin/` (the rotation entries Exec it by absolute path -
  graphical launches do not inherit the interactive-shell PATH). Helper is a FAITHFUL copy of
  the stow `scripts` package's `rotate_screen` (only a MANAGED-BY-ANSIBLE header added,
  `~/.scripts` -> `~/.local/bin`, `->` ASCII-normalized in comments). SANITIZATION: source
  held no private data (no username / real home paths); Japanese `GenericName` -> English.
  Ported-as-is quirks KEPT (documented in README): unquoted `[ -n $WAYLAND_DISPLAY ]` (X11
  branch dead; fine on the user's Wayland), `output.1` hardcoded, short CLI flags verbatim.
  Wired: `playbooks/kde_touchscreen_desktop_entries.yml`, `make
  apply-kde-touchscreen-desktop-entries` / `check-...` (+ `.PHONY`), README. No gate (the
  `setup_*` model is gone). VERIFIED: `bash -n` + `--syntax-check`; end-to-end on a throwaway
  `target_home` (all 7 files land, run2 `changed=0`, render correct, 0 leftover Jinja, 0
  non-ASCII); stow-symlink guard refuses with the `stow --delete xdg-desktop-screen-rotation`
  hint and writes 0 files through the link. PENDING on the real host: `stow --delete
  xdg-desktop-screen-rotation`, `make apply-kde-touchscreen-desktop-entries`, then confirm the
  menu entries appear and rotation works on the touchscreen.

## quickemu_vm role + `qvm` launcher (v1 built; needs a real-host run)

Sibling of `ivm` on the axis incus can't do (Windows/macOS guests, 3D desktop
Linux - see `roles/incus_vm/docs/survey-of-quickemu.md`), built to the user's
"no interactive installs for debian/TW/fedora" requirement. Role-local detail +
the template-sharing design discussion: `roles/quickemu_vm/TODO.md`.

- [x] **`qvm` launcher** (`files/qvm`, typed Python, stdlib only; 15 unit tests) -
  `init` prebuilt paths: tumbleweed = official Minimal-VM Cloud qcow2
  (sha256-verified, cached) + cloud-init NoCloud seed ISO (key-only user,
  installs qemu-guest-agent on first boot); debian/fedora = `virt-builder`
  (GPG-verified, agent+sshd baked in, per-VM ed25519 on root); anything else =
  `quickget` passthrough (Windows unattended), conf adopted. Lifecycle:
  start (headless default / `--gui` SPICE), stop (ACPI via the HMP monitor
  socket - no agent needed, Windows too), kill, delete (y/N), list, info.
  `exec`/`push`/`pull` via the QEMU Guest Agent socket (batch only - QGA has no
  PTY, upstream-documented); interactive `shell` = SSH on quickemu's
  auto-forwarded port (per-VM key + per-VM known_hosts). `snapshot` =
  qcow2-internal passthrough (refused while running, except `info`). cwd
  binding via per-VM `qvm-meta.json` (nearest ancestor) + global `--name`.
  quickemu runtime contract verified against `REFS/quickemu` @ 2d9f6c9.
- [x] **zsh + bash completions** - same `ansible-managed/*/{zsh,bash}-completions`
  auto-discovery as ivm; `--name` completes from `$QVM_HOME/vms/*.conf` stems.
- [x] **Role + playbooks + Makefile + gates + READMEs** - host pkgs all
  probe-gated: `quickemu` (Debian 13+/Fedora 41+ OFFICIAL repos; openSUSE ships
  NONE - loud warn + manual steps, role continues), `guestfs-tools`
  (virt-builder; all 3 families incl. TW/Leap - repology 2026-06), `xorriso`
  (seed ISO; skipped when genisoimage/mkisofs present). `make
  quickemu-install/check/uninstall-qvm`; `setup_quickemu_vm` gate (default
  false). VM data lives at `~/.local/share/qvm/` OUTSIDE ansible-managed/ ->
  uninstall can never erase a VM. Verified: both playbooks syntax-check,
  `make -n`, e2e in the sandbox env (install -> rerun changed=0 -> uninstall
  clean, VM data dir untouched).
- [ ] **Real-host validation** (no KVM in this env): TW first boot (cloud-init
  installs the agent) -> `qvm exec`; debian/fedora virt-builder path;
  `qvm init windows 11` unattended; offline snapshot create/apply.
- [ ] **VERIFY: TW Minimal-VM `-Cloud` image - is `qemu-guest-agent`
  preinstalled?** If yes, drop the seed's `packages:` step (faster first exec).
- [ ] **(ivm, separate pass) `templates/base_{debian,opensusetw,fedora}.yaml`** -
  bare guests, baseline + `basic_tools` only (user request). Symmetry once done:
  `ivm init base_opensusetw` <-> `qvm init tumbleweed`. Template-sharing
  decision recorded in `roles/quickemu_vm/TODO.md`: qvm copies NO ivm templates
  (capability sets differ); the real sharing seam is the `distro_packages`
  registry JSON (future `qvm provision`); role renaming (`vm_incus`/`vm_quickemu`)
  deferred.

## vm_podman (`pvm`) - REFACTOR.md Phase 3 (container engine)

Fold `container_apps` + `container_templates` into ONE engine role `roles/vm_podman`
shipping `pvm`, mirroring `vm_quickemu`/`qvm`. Dockerfile-less: provision a base
container via `podman exec`/`cp` then `podman commit` (content-hash tag); consume
the SAME shared provision-asset cache ivm/qvm use. crun in v1; libkrun deferred.
Full plan: `roles/vm_podman/IMPLEMENTATION_PLAN.md`.

- [x] **3.0 scaffold** - `roles/vm_podman` mirroring `vm_quickemu`: `files/pvm`
  skeleton (env/list/help wired; other subcommands registered but error with the
  sub-phase that adds them), `test_pvm.py`, `_pvm`/`pvm.bash` completions, defaults,
  tasks (main/pvm_install/pvm_uninstall/podman_host_install), README, playbooks,
  sandbox config, Makefile `vm-podman-*`. ivm/qvm/pvm uninstall upgraded to a 3-way
  shared-cache ref-count (pvm is now a third consumer). (Repo-hygiene git-rm was a
  no-op: the dead `roles/incus_vm` cruft + `.pyc` are untracked, already gitignored.)
- [x] **3.1** declarative templates + `template.schema.json` + port `host-cli.sh.j2`
  logic + `filter_plugins/distro.py` to typed Python (pure, unit-tested; no podman).
- [x] **3.2** consume the shared cache: provision-via-exec + `podman commit`
  (content-hash); `overlay/workspace-autocd`; dynamic completions read the JSON.
- [x] **3.3** real podman drive (init/run/lifecycle/shell/agent, crun) + isolation
  guardrails (shared-kernel warn -> ivm; non-libkrun `init` [y/N] gate).
- [x] **3.4** retire `container_apps` + `container_templates`; tick REFACTOR.md.
- [ ] **(deferred) libkrun** - `--runtime krun` + sshd-via-commit (recipe in the plan).

## ivm llm_* templates: sillytavern rename + openwebui/librechat appliances

- [x] rename `sillytavern.yaml` -> `llm_sillytavern.yaml` (template_name + header
  comment; in-guest helper `st-backup` -> `llm-backup`, tar dir/prefix unchanged so
  old backups keep listing)
- [x] `[IDEMPOTENCE]` removal of the stale deployed `templates/sillytavern.yaml` in
  `tasks/ivm_install.yml` (the templates `copy` never purges)
- [x] new `llm_openwebui.yaml`: first `podman_rootless` bundle consumer; upstream's
  official container via a rootless `podman run` per-user unit (host -> guest:8080);
  in-guest `llm-backup` (tars `~/openwebui` to `~/Downloads/OpenWebUIBackups/`)
- [x] new `llm_librechat.yaml`: upstream compose trimmed to api+mongodb via a
  `podman-compose` per-user unit (host -> guest:3080); one-time `.env` secrets
  (CREDS_* decrypt stored keys -> .env is inside the backup set); in-guest
  `llm-backup` (tars `~/librechat` to `~/Downloads/LibreChatBackups/`)
- [x] `roles/vm_incus/README.md` shipped-examples list updated (it already omitted
  sillytavern; now lists the three `llm_*` appliances)
- [x] two-tag VM binding (appliances resolve by NAME, not cwd):
  `user.ivm_init_at_dir` demoted to pure history (+ managed marker); resolution
  reads the new `user.ivm_host_bound_dir`, written at init from the REQUIRED
  template field `host_bound_dir` (host-expanded; `$(pwd)` = project box) - a
  real dir (bound) or NO tag (unbound: `""` in all 3 `llm_*` appliance
  templates / `ivm unset host-bound-dir` / legacy pre-tag VM; no sentinel -
  absent and empty read back identically everywhere). Unbound/legacy never match, never auto-fallback;
  no-match error lists both with copyable commands. New `ivm set host-bound-dir
  [<dir>]` (no arg = cwd; also the legacy migration) / `unset` (removes the tag);
  `set shell-dir` renamed `guest-shell-dir` (completions now say HOST vs GUEST);
  `ivm info` gains host-bound-dir + guest-shell-dir fields; `ivm cd`/`list` show
  labelled placeholders; appliance default name `ivm-<template>` (no path
  suffix); schema + README/SPEC/DESIGN updated
- [x] llm_sillytavern: ship the CharacterLibrary extension by default (full git
  clone into `data/default-user/extensions/`, guarded, AFTER the ST clone) +
  `enableCorsProxy: true` in config.yaml (its embedded-media downloads).
  Upgrade = `git -C <extension dir> pull` or ST's Extensions Update button;
  lives under data/ so llm-backup already carries it. cl-helper SERVER plugin
  deliberately not installed (needs enableServerPlugins; README has the recipe)
- [x] llm_librechat: `user_provided` apiKey never fetches the live model list
  (upstream LibreChat#4500/#1028, open since 2023) - dropdown showed only the
  `default` fallback. Switched the shipped config to `${OPENROUTER_KEY}` from
  .env (server-side fetch works; .env is already in the backup set) + new
  in-guest one-command setter `llm-key <key>` (writes .env, restarts api; init
  ready message + description point at it) - setting a key never means editing
  a file
- [x] (Regression, hit on real init) llm_librechat init-hang TRUE root cause:
  `npm run create-user` (v0.8.7) interactively asks "Email verified? (Y/n)" even
  with all four positional args - `podman exec` without stdin sits on that prompt
  forever (main-branch source suggested args suffice; version drift). Fixed by
  passing `--email-verified=true` explicitly; confirmed from the user's own
  interactive run output
- [x] (Regression, hit on real init) llm_librechat: removing upstream's compose
  `restart:` policies was WRONG - the systemd unit supervises only the
  podman-compose process, not member containers; when the api crashed (exit 1
  after ~7 min, root cause TBD from its log tail) podman-compose stayed attached
  to mongo, the unit stayed active, and nothing restarted the api (this is also
  what starved the init account loop). `restart: unless-stopped` restored on both
  services - podman's own policy is the only member-level supervisor
- [x] (Regression, hit on real init) llm_librechat default-account retry loop sat
  SILENT for minutes (mongoose ~30s connect timeouts x 60 attempts, no output ->
  read as a hang; violated the fail-loudly rule). Fixed: progress line every
  attempt, `timeout 20` per attempt, stdin `< /dev/null` (an unexpected prompt
  fails fast instead of hanging), 30 attempts, and the block moved to the LAST
  post_install step so an interrupt loses nothing else
- [x] llm_openwebui: OpenRouter pre-wired via `--env OPENAI_API_BASE_URL=...` on the
  `podman run` line - a FIRST-LAUNCH seed only (Open WebUI PersistentConfig: after
  first boot the UI-stored value under `~/openwebui/data` wins, env ignored), so
  later Admin Settings -> Connections edits stick; both llm_openwebui and
  llm_librechat `description:` now state OpenRouter is pre-wired (paste key in UI)
- [x] llm_librechat usability pass (from first real use): ship
  `~/librechat/librechat.yaml` (guarded like .env) with OpenRouter as a
  `user_provided` custom endpoint (key pasted in the web UI -> mongo, encrypted
  with CREDS_* -> rides llm-backup; docs-verbatim `dropParams: ["stop"]` +
  `fetch: true`), mounted via compose `./librechat.yaml:/app/librechat.yaml`;
  pre-create default account `admin@example.com / adminadmin` at init
  (`npm run create-user` inside the api container, retried until mongo is up,
  "already exists" = idempotent re-init; password is admin twice because the
  LOGIN form also enforces `MIN_PASSWORD_LENGTH` >= 8) and flip
  `ALLOW_REGISTRATION=false` (add accounts via create-user; .env documents it)
- [x] llm_librechat api `EACCES: permission denied, open /app/logs/...` (hit on the
  first real init): the api image runs as `node` (container uid 1000, `USER node`)
  while rootless podman maps the guest user to container uid 0, so the mkdir'd
  bind mounts were container-root-owned. Init now `podman unshare chown`s
  logs/uploads/images to the container node uid; `data-node` untouched (mongo's
  entrypoint self-chowns); `userns_mode: keep-id` was no fix (podman-compose pod
  vs `--userns` conflict, podman-compose#654)
- [x] (Regression, caught in review) zsh VM-name completion lost its dir
  descriptions for existing VMs when `_ivm_vms_with_dir` switched to the new
  `user.ivm_host_bound_dir` tag (pre-tag VMs have none -> bare names). Fixed:
  description = bound dir when present, else `(unbound; init dir
  <user.ivm_init_at_dir>)` - every managed VM keeps a dir column; python3-csv
  parse (two dir columns defeat the split-on-first-comma trick); `cd` candidates
  decoupled so unbound VMs stay out of them
- [x] `services` template annotation (`name: port` map, e.g. `webui: 8080` on all
  3 `llm_*`): written to `user.ivm_services` at init, `ivm info` Network gains a
  `services` row printing ready-to-open `name=<ip>:<port>` (placeholders when
  undeclared / no live ip); also shown at init (confirm preview with `<guest-ip>`
  stand-in + ready message with the LIVE ip) and in `ivm env`; init warns when a
  declared port literal is missing from `post_install_script` (stale-declaration
  tripwire; annotation, NOT an input - scripts keep hardcoding their ports)
- [x] verify (structural): 3 templates pass template.schema.json (draft 2020-12,
  ajv; `template_name` matches filename), `bash -n` passes on every
  `post_install_script` + all 3 embedded `llm-backup` scripts, compose heredoc +
  `tasks/ivm_install.yml` YAML-parse clean
- [ ] verify (host): `make vm-incus-check` + `make vm-incus-sandbox` - the editing
  devcontainer has no ansible/podman (and sudo prompts); run on a provisioned host
- [x] new `llm_risuai.yaml` (RisuAI = the other character-card chat frontend; mirrors
  llm_sillytavern's clone-and-run shape): built from SOURCE with upstream's self-host
  build flag `VITE_RISU_LEGAL_CONFIGURED=TRUE` - the official ghcr image is built
  without it and boots into the "Legal documents not configured" wall (upstream
  #1466, open) - via user-scoped pnpm (`~/.local/bin`, version from package.json
  `packageManager`); served over HTTPS with upstream's own self-signed-cert generator
  because the node-mode login signs requests with WebCrypto (`crypto.subtle`), which
  browsers expose only on secure origins - plain `http://<guest-ip>` cannot load any
  data; per-user unit `risuai` (host -> guest:6001, `services` declared); in-guest
  `llm-backup` (tars `~/RisuAI/save` to `~/Downloads/RisuAIBackups/`); `usage:` notes
  (https + cert warning, set-then-enter password flow, upgrade one-liner); README
  shipped-examples list updated
- [x] verify (structural, llm_risuai): passes template.schema.json via ivm's own
  `load_and_validate` (PyYAML + jsonschema in a scratch venv), `services` tripwire
  clean, `bash -n` on `post_install_script` + the embedded `llm-backup`
- [x] (hit on real init) llm_risuai: `pnpm install` looked stuck "fetching CUDA" -
  RisuAI's `pnpm.neverBuiltDependencies: [sharp]` re-enables every other dependency's
  install script in pnpm 10 (its 10.0 release notes), so onnxruntime-node 1.21.0 (a
  Node-only dep of @huggingface/transformers) ran its postinstall = download of the
  hundreds-of-MB `onnxruntime-linux-x64-gpu-<ver>.tgz` with no progress output. The
  browser bundle uses onnxruntime-web (WASM), so the script's own switch
  `ONNXRUNTIME_NODE_INSTALL_CUDA=skip` now wraps the install (init + the `usage:`
  upgrade one-liner)
- [x] `scripts/risuai-upgrade` (`ivm --name <vm> script risuai-upgrade`, llm_risuai VMs
  only): `git pull --ff-only` -> skip when HEAD unchanged + dist exists -> `pnpm install`
  with ONNXRUNTIME_NODE_INSTALL_CUDA=skip -> `pnpm run build` with
  VITE_RISU_LEGAL_CONFIGURED=TRUE -> restart the unit; both build-time env vars live in
  the script, the `usage:` upgrade note points at it instead of a 5-part one-liner.
  Lib gained `guest_run` (announce + run + die) and `guest_succeeds` (silent probe);
  unit control now builds on `guest_run`
- [x] (hit on real init) llm_risuai: the ready message / `ivm info` printed
  `webui=<ip>:6001` with no scheme, so the address was opened as http - which cannot
  even connect (the port speaks TLS). `services` entries may now declare a scheme
  (`webui: {port: 6001, scheme: https}`, schema `oneOf` next to the bare port); every
  surface prints `name=https://<ip>:<port>` for them (`ServiceEndpoint` +
  `declared_service_endpoints` / `services_tag_value` / `parse_services_tag` /
  `format_service_endpoints`); `info` reads the entries LIVE from the template (like
  `usage`), tag `name:scheme:port` as the fallback - so the existing VM shows https
  right after `make vm-incus-install`, no re-tag
- [ ] verify (host, llm_risuai): first real `ivm init llm_risuai` - the vite build fits
  in 4G, the https self-signed warning click-through, set-then-enter password flow,
  `llm-backup` round trip; plus `make vm-incus-sandbox` (no podman in the editing env)

## ivm script framework (host-side helper scripts) - backup / restore as its first two

- [x] problem: each llm_* template baked its own ~65-line `llm-backup` bash copy into
  the VM at init - a template fix never reached existing VMs (the same staleness
  `usage:` was moved to a live read for). First cut (d2e1326, kept as a checkpoint)
  made `backup` / `restore` dedicated ivm subcommands - too specialized: every new
  per-VM helper would mean more ivm Python. Replaced by a generic framework
- [x] `ivm [--name <vm>] script [<script> [args...]]`: runs `<root>/scripts/<script>` on
  the HOST against the VM (started first) with `IVM_VM` / `IVM_TEMPLATE` /
  `IVM_TEMPLATE_FILE` / `IVM_ROOT` / `IVM_YES` in env, args verbatim, process
  replaced (stdin/stdout/exit code are the script's); `--dry-run` prints + runs
  nothing; no script name lists them + `# description:` headers. Runnable = executable
  + not `_`-prefixed (`_`-prefixed = shared libs). Host-vs-guest: scripts run on the
  host and reach the guest via `incus exec` (data over its stdin/stdout - no share
  needed), the same model as ivm itself; `_ivm_script_lib.py` carries the as-`user` +
  D-Bus-env exec incantation, user-unit control, die/announce
- [x] `scripts/backup` + `scripts/restore` (+ `_ivm_backup_lib.py`): the template's
  `backup:` block (schema: `unit` / `dir` / `paths[]` / `podman_unshare` /
  `host_downloads_subdir`), read LIVE via `IVM_TEMPLATE_FILE` - a fix applies to every
  existing VM, old ones included. backup: stop the unit (restarted only if it was
  running), `tar --create` as `user` (in `podman unshare` when declared) streamed into
  `<xdg DOWNLOAD>/<subdir>/<vm>_<stamp>.tar`, partial file removed on failure.
  restore `[<file>|latest]`: prints what it overwrites + confirms (`IVM_YES`), stop,
  `tar --extract` from stdin, start; `latest` = newest `*.tar` (old `STBackup_*` etc.
  included); bare filename looked up in the dir; no arg lists the VM's backups
- [x] 4 llm_* templates: `backup:` block, embedded `llm-backup` heredocs removed
  (~260 lines), `usage:` lines point at `ivm --name <vm> script backup` / `... restore
  latest`; the ~/Downloads mount dropped from openwebui / librechat / risuai (it
  existed only for the in-guest tars; ST keeps it as the character-card drop zone).
  Existing VMs keep their old in-guest copy - harmless, just no longer the documented
  path
- [x] `scripts/st-vm-backup` retired (ST-only, hot backup without a unit stop, no
  completion, not in the Makefile)
- [x] deploy: `tasks/ivm_install.yml` copies `files/scripts/` to `<root>/scripts/`
  (`mode: preserve` keeps +x); uninstall already removes the whole role subdir
- [x] completions: `_ivm` (`script` -> script names + descriptions via `_describe`, then
  host files for the script's args) + `ivm.bash`; SPEC 2a/3 + README rows + files table
- [x] script env = the SOURCE identifiers, never renamed (user feedback): every
  `user.ivm_<tag>` on the VM is exported as `IVM_<TAG>` (tag uppercased; absent tag =
  absent variable; `IVM_TEMPLATE` always set) - scripts never re-learn tag names, a
  future tag comes for free; plus `IVM_PRIMARY_IPV4` (ivm's `vm_primary_ipv4`),
  `IVM_ROOT` + `SHARED_PREBUILT_PROVISION_ASSETS_ROOT` (the env names ivm itself
  honors), `IVM_YES`; cwd inherited from the caller + argv verbatim now written into
  the contract (ivm docstring, `_ivm_script_lib.py`, SPEC, README)
- [x] verify (structural): py_compile (ivm + the 4 script files), `ivm script --help`,
  all templates pass the schema, `bash -n` on the 4 `post_install_script`s, `bash -n`
  ivm.bash, `zsh -n` _ivm, and a REAL local backup -> restore round trip through
  `ivm --root <scratch> script ...` with a fake `incus` on PATH that runs the guest-side
  argv locally
- [ ] verify (host): real round trip on one podman appliance (the unshare path) and
  one plain one (ST or risuai); `make vm-incus-sandbox`

## fcitx5_quick_phrase role: Quick Phrase files (built + verified on a scratch home; needs a real-host run)

- [x] **`roles/fcitx5_quick_phrase` + `playbooks/fcitx5_quick_phrase.yml` + `make
  apply-fcitx5-quick-phrase` / `check-fcitx5-quick-phrase`** -
  config-style face role (like `mpv`): copies `files/quickphrase.d/*.mb` to
  `~/.local/share/fcitx5/data/quickphrase.d/` (fcitx5 merges every `.mb` there into ONE
  table - a keyword in two files lists both candidates), then reloads the `quickphrase`
  addon over D-Bus (`busctl --user call org.fcitx.Fcitx5 /controller
  org.fcitx.Fcitx.Controller1 ReloadAddonConfig s quickphrase`) when a file changed and
  `fcitx5-remote --check` says fcitx5 is running; otherwise prints a note (read at next
  start). `fcitx5-remote -r` is NOT enough: `Instance::reloadConfig` reloads only the
  global config, never an addon's data files (fcitx/fcitx5 `src/lib/fcitx/instance.cpp`).
  First file: `llm.mb` - keyword `d` -> the standing LLM prompt preamble.
- [ ] verify (host): `make apply-fcitx5-quick-phrase`, then `Super+grave` (or
  `Super+semicolon`), type `d`, pick the phrase; re-run = no change, no reload.
- [x] scope: Quick Phrase files only. The chewing keys + IM profile script
  (`roles/vm_incus/files/setup-fcitx5-input.sh`) is NOT folded in here - a general
  `roles/fcitx5` for it stays deferred (the "fcitx5 host-side wiring" item above).

## Notes / future

- [x] **container_apps -> one engine + declarative templates** - DONE as
  REFACTOR.md Phase 3 (`pvm` / `roles/vm_podman`); see the dedicated section above +
  `roles/vm_podman/IMPLEMENTATION_PLAN.md`. (Working name resolved `capp` -> `pvm`;
  the `filter_plugins/__pycache__/*.pyc` "committed cruft" note was stale - they are
  untracked + already gitignored.)
- Python launcher rewrite: deferred to the `incus_vm` redesign (see
  `roles/incus_vm/REDESIGN.md`). Trigger = presets / multi-distro /
  Windows. The 11 duplicated subcommands across the two launchers get unified
  there.
- Runtime-unverifiable here (no incus in this env): the `root -> /` push landing
  at `/root`, and `incus list/config get` filtering. Logic is sound; confirm on
  a real incus host.
