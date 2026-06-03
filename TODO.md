# TODO

Durable mirror of the in-session task list (the task tool is local/ephemeral;
this file is the git-tracked, cross-machine source of truth). Keep in sync.

Status: `[ ]` pending · `[~]` in progress · `[x]` done · `[blocked: #N]`

## incus launcher improvements

- [x] **1. Decide launcher language (bash vs Python)** -> **bash now.**
  Python rewrite deferred to the bigger `incus-workspaces` redesign (presets /
  multi-distro / Windows; see `roles/incus_workstations/REDESIGN.md` §4.6),
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

## Notes / future

- Python launcher rewrite: deferred to the `incus-workspaces` redesign (see
  `roles/incus_workstations/REDESIGN.md`). Trigger = presets / multi-distro /
  Windows. The 11 duplicated subcommands across the two launchers get unified
  there.
- Runtime-unverifiable here (no incus in this env): the `root -> /` push landing
  at `/root`, and `incus list/config get` filtering. Logic is sound; confirm on
  a real incus host.
