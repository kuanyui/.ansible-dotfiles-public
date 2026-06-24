# roles/vm_incus TODO

Durable, role-local notes (same convention as the repo-root TODO.md).
Status: `[ ]` pending · `[~]` in progress · `[x]` done

## `ivm set`/`unset <aspect>` namespace - replace flat `set-*`/`unset-*` verbs - PLAN (2026-06-24)

### Background: how `ivm`'s CLI is wired TODAY (read this first - every step edits these)

`roles/vm_incus/files/ivm` is ONE ~2772-line Python script, `argparse`-based and
METADATA-DRIVEN: a few module-level tables describe the subcommands, and both `build_parser()`
and `main()` loop/branch over those tables. Line numbers are approximate (they shift as we edit)
- grep the name if it moved.

- **`CWD_RESOLVED`** (tuple, ~L73): the subcommands that act on ONE existing VM, resolved by the
  current directory (the VM's `user.ivm_init_at_dir` tag) or the global `--name <vm>`. The 6 verbs
  we are deleting all live in here. (`init`/`env`/`list`/`adopt`/... are NOT here - they don't
  target a cwd-bound VM.)
- **`CWD_RESOLVED_HELP`** (dict, ~L81): subcommand name -> its one-line `--help` blurb. Keys must
  match `CWD_RESOLVED` exactly.
- **`CWD_RESOLVED_HANDLER`** (dict, ~L2543): subcommand name -> the `cmd_*()` function that runs it.
- **`PASSWORD_SUBCOMMANDS`** (~L122) / **`SSH_SERVER_SUBCOMMANDS`** (~L125): which subcommands get a
  positional `username` arg (and, for ssh, a repeatable `--pubkey`). `build_parser` reads these to
  decide which args to add. Both go away (folded into the aspect registry).
- **`build_parser()`** (~L2556): builds the argparse tree. Special subcommands (`init`/`env`/`adopt`/
  `mount`/...) are added by hand; the rest by a `for name in CWD_RESOLVED:` loop (~L2604) with
  `if name == "<x>":` blocks that add per-subcommand args. **`mount` (~L2624) is the existing
  TWO-LEVEL example** (`mount` -> `ls`/`attach`/`shadow`/`detach` via a nested `add_subparsers`) -
  COPY its shape for `set`/`unset` -> `<aspect>`.
- **`main()`** (~L2658): parse args, fold aliases, then EARLY-RETURN the non-VM subcommands
  (list/top/init/env/adopt/storage-status, and `provision` with no units = "just list units"),
  THEN at ~L2709 resolve the target VM (`--name` else cwd), THEN a big `if/elif args.subcommand
  == ...:` chain (~L2710) calls the matching `cmd_*` handler. (Our bare `set`/`unset` "list the
  aspects" case must early-return BEFORE the VM resolution, like provision-no-units does.)
- **The 6 handlers are KEPT, only re-wired** (not rewritten): `cmd_set_password` (~L1623),
  `cmd_unset_password` (~L1645), `cmd_enable_user_sudo` (~L1662), `cmd_disable_user_sudo` (~L1675),
  `cmd_set_ssh_server` (~L1683), `cmd_unset_ssh_server` (~L1710).
- **The `shell-dir` feature is HALF-built already**: a template's `shell_default_dir_after_login`
  field (schema L125) is written at `init` (~L590) to the VM tag
  `user.ivm_shell_default_dir_after_login`; `shell_login_dir()` (~L1500) reads that tag at `ivm sh`
  time and passes `incus exec --cwd <dir>`, with a `test -d` probe that warns + falls back to the
  default cwd if the dir is missing. WHAT'S MISSING (= the new `shell-dir` aspect): any way to
  set/clear that tag AFTER init. (`adopt`'s tag list at ~L2484 does NOT include it.)
- **Completions are SEPARATE, hand-maintained files** (NOT generated from the tables above), so they
  must be edited by hand every time: `completions/_ivm` (zsh) and `completions/ivm.bash` (bash).
  Each has its own subcommand list + a per-subcommand `case`. Their `mount)` and `snapshot)` cases
  are the existing TWO-LEVEL models to copy for `set)`/`unset)`.

**Why.** 6 flat verbs clutter the top level and more are coming (`git-ssh`, ...). Group into
`ivm set <aspect>` / `ivm unset <aspect>` (mirrors `incus config set`; ivm exists to LOWER
incus's mental load, so the namespace must add none). FULL symmetry: every aspect has BOTH
`set` and `unset`, zero special cases.

**Final surface** (aspects: `password`, `ssh-server`, `shell-dir` [NEW], `user-sudo`):
- `set`/`unset password <user>`
- `set`/`unset ssh-server <user> [--pubkey FILE ...]`
- `set shell-dir <path>` / `unset shell-dir`
- `set user-sudo` / `unset user-sudo`   (replaces `enable-user-sudo`/`disable-user-sudo`)
- `ivm set` / `ivm unset` with NO aspect -> list aspects + descriptions (zsh AND bash)

**Removed (6 flat verbs):** `set-password unset-password set-ssh-server unset-ssh-server
enable-user-sudo disable-user-sudo`. Footprint to scrub: `ivm`=34, `_ivm`=9, `ivm.bash`=3.

**Steps** (verify each):
- [ ] 1. `ivm` metadata: drop the 6 from `CWD_RESOLVED`/`CWD_RESOLVED_HELP`/`CWD_RESOLVED_HANDLER`;
  drop `PASSWORD_SUBCOMMANDS`/`SSH_SERVER_SUBCOMMANDS`; add a `SET_UNSET_ASPECTS` registry
  (aspect -> set_help, unset_help) as the single source for parser + listing + completion intent.
- [ ] 2. `ivm` handlers: add `cmd_set_shell_dir(name, path)` (`incus config set <vm>
  user.ivm_shell_default_dir_after_login <path>`; NO `ensure_up` - runtime `shell_login_dir`
  already `test -d`-warns + falls back) + `cmd_unset_shell_dir(name)` (`incus config unset`).
  Keep `cmd_set_password`/`unset_password`/`set_ssh_server`/`unset_ssh_server`/`enable_user_sudo`/
  `disable_user_sudo` AS-IS (only re-wired, not rewritten).
- [ ] 3. `ivm` `build_parser`: add `set` + `unset` nested subparsers (aspect subparser NOT
  `required=True` -> a bare `set`/`unset` lists); per-aspect args (username: password+ssh-server;
  `--pubkey`: ssh-server; `path`: `set shell-dir` ONLY; none: user-sudo and `unset shell-dir`).
  Model on the existing `mount` 2-level block.
- [ ] 4. `ivm` `main()`: bare `set`/`unset` (no aspect) -> `cmd_list_set_aspects(verb)` BEFORE the
  cwd VM resolution; else resolve the VM then dispatch by (verb, aspect); `set/unset user-sudo` ->
  `cmd_enable/disable_user_sudo`. Delete the 6 flat `elif` branches. Add `cmd_list_set_aspects()`.
- [ ] 5. `ivm` header docstring (~lines 12-13): swap the 6 verbs in the "Implemented:" prose for
  `set`/`unset`.
- [ ] 6. **zsh `_ivm`**: delete the 6 from `_ivm_subcommands`; add `set`/`unset`; delete the 2 old
  arg-cases (`set-password|unset-password`, `set-ssh-server|unset-ssh-server`); add `set)`/`unset)`
  2-level (aspect via `_describe`, then per-aspect: `user root` for password; `user root --pubkey`
  + `_files` for ssh-server; `_message 'absolute guest dir'` for `set shell-dir`; nothing for
  user-sudo / `unset shell-dir`). Model on the `mount)` case.
- [ ] 7. **bash `ivm.bash`**: update the `subcommands` string; delete the 2 old cases; add
  `set)`/`unset)` 2-level mirroring zsh. Model on the `mount)` case.
- [ ] 8. Verify: `python3 -m py_compile ivm`; smoke `ivm --help`, `ivm set`, `ivm unset` (both
  list), `ivm set password --help`, `ivm set shell-dir --help`, `ivm --name X set user-sudo
  --dry-run`; `bash -n` both completions; `grep -E '(set|unset)-(password|ssh-server)|(en|dis)able-user-sudo'`
  over `ivm` + both completions + header == 0; `make vm-incus-sandbox`.

**DO-NOT-FORGET** (historically missed): BOTH completions (zsh `_ivm` AND bash `ivm.bash`);
bare `set`/`unset` must LIST (bash too, per CLAUDE.md); the final grep of the 6 old verbs must be
ZERO everywhere (ivm + both completions + header + README/docs).

**PARKED (needs user decision, SKIPPED for now):** `REDESIGN.md` (~L458) and
`IMPLEMENTATION_PLAN.md` (~L22-28) still list the 6 old verbs. They are point-in-time design /
implementation-plan records, so revising them is arguably rewriting history. Decide: reconcile to
the `set`/`unset` namespace (consistency), or leave as historical record with a "superseded" note?
(`README.md`, `survey-of-quickemu.md`, and the `ivm` code/completions ARE updated.) The kept
`/etc/ssh/sshd_config.d/ivm-set-ssh-server.conf` filename is an internal artifact, deliberately NOT
renamed (renaming would orphan the file on already-configured VMs).

## `ivm release-ram` - reclaim a running VM's host RAM without stopping it (NOT built)

Deferred on purpose: the user wants to confirm the real behavior on a host before we
build it. Recorded here so it is not re-derived.

**Why it is needed.** incus VMs have NO virtio-balloon **free-page-reporting** (verified
in incus source: `internal/server/instance/drivers/driver_qemu_templates.go` -
`qemuBalloon()` emits a plain `virtio-balloon-pci` with no `free-page-reporting`; QEMU
defaults that property off). So a running VM's host RSS is the **high-water-mark** of
pages the guest ever touched and is **NOT returned to the host until the VM stops**. The
only non-stop lever is the balloon.

**Mechanism to wrap (the balloon squeeze).**
- `incus config set <vm> limits.memory=<lower>` -> incus inflates the balloon
  (`driver_qemu.go:updateMemoryLimit`, via QMP `SetMemoryBalloonSizeBytes`, polling until
  the effective size shrinks within 1%) -> guest frees pages -> host reclaims.
- then restore `incus config set <vm> limits.memory=<original>`.

**Caveats (all verified / documented).**
- SLOW and may not hit the target in one pass; re-applying the lower value triggers
  another attempt (see incus issue #1904 - documents the timeout/desync).
- Hot **raise** back only works on incus **6.12+**; older incus needs a restart to grow.
- The balloon can only reclaim **free/reclaimable** guest memory - so it is far more
  effective now that the shipped templates leave `/tmp` on disk (reclaimable page cache)
  than with `sys.tmpfs /tmp` (used memory, stuck unless the guest has swap).
- Squeezing too low can OOM the guest.

**Open questions before building.**
- Pick the squeeze target (guest-used + headroom? a fixed fraction of `limits.memory`?).
- Auto-restore vs require the user to restore; gate hot-restore on incus >= 6.12.
- Confirm on a real host what lowering/restoring `limits.memory` actually does to the
  QEMU RSS (the env here has no incus).

**Until then.** `ivm stop` (then `ivm start`) is the reliable full reclaim. `ivm top`
gives a quick per-instance glance, but a VM's memory there is GUEST-reported and
under-reports the host RSS - use `ps -eo pid,rss,comm --sort=-rss | grep qemu` for the
true host cost.
