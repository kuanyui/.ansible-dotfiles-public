# TODO

Durable mirror of the in-session task list (the task tool is local/ephemeral;
this file is the git-tracked, cross-machine source of truth). Keep in sync.

Status: `[ ]` pending · `[~]` in progress · `[x]` done · `[blocked: #N]`

## incus launcher improvements

- [~] **1. Decide launcher language (bash vs Python)** - gates #2/#3.
  Assessment done: #1/#2/#4 are small in bash; the Python rewrite belongs to
  the bigger `incus-workspaces` redesign (see
  `roles/incus_workstations/REDESIGN.md` §4.6), not piecemeal now. The real
  smell is the 11 duplicated subcommands across the two ~950-line launchers.
  **Awaiting user's go-ahead: "bash now, Python at the big redesign".**

- [ ] **2. `init` preview + y/N confirm** [blocked: #1].
  On first-time `v-<name> init`, print BEFORE acting: resolved project/cwd, VM
  name, mounts, VM spec (cpu/mem/disk/image); then y/N gate. Prevents
  "forgot to cd" mistakes. Mainly the `incus_agents` launcher (cwd-derived name).

- [ ] **3. Open an existing VM by name (with completion), no cd needed** [blocked: #1].
  Attach to an already-created VM by name without cd-ing into its project dir;
  shell-completion of existing VM names; sets HOME/USER/cwd env correctly so the
  user need not hand-run `incus exec` with all the env. Scoped to our own VMs.

- [ ] **4. Makefile `incus-overwrite-dotfiles-in-all-guest`** (our own Linux guests only).
  Re-push the staged dotfiles (user+root trees) into ALL our own Linux incus
  guests at once. Scope to (a) only VMs we created, (b) only Linux (exclude
  future Windows) - likely via incus `user.*` config tags set at VM-launch time
  in the launchers. Supersedes/extends `resync-incus-agents-dotfiles`.
