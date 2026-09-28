# ivm SPEC (normative)

What `ivm` MUST do - the contract, independent of how it is coded. Pairs with
[`DESIGN.md`](DESIGN.md) (how/why it is built) and [`README.md`](README.md) (how
to use it). When this file and the code disagree, that is a bug in one of them;
this file is the intended behavior.

Terms used throughout:

| Term | Meaning |
|---|---|
| **incus** | system container + VM manager (LXD fork). `ivm` only ever wraps its CLI. |
| **VM** | a full-kernel KVM guest (not a container). |
| **agent** | the `incus-agent` running INSIDE the guest; `incus exec` talks to it. |
| **virtio-fs** | paravirtualized filesystem - shares a host directory into the guest live. |
| **`user-<uid>` project** | incus's per-user RESTRICTED project that the `incus` group maps into (NOT `default`). |
| **`ansible_os_family`** | the ansible fact (`Debian` / `Suse` / `RedHat`), derived from `os.distro`. |

## 1. Purpose + non-goals

**Purpose.** Create and manage host-provisioned incus KVM VMs from declarative
YAML templates, one VM per project directory, with the guest kept free of any
ansible/python (all provisioning is driven from the host via `incus exec`).

**Non-goals.**
- NOT a generic incus wrapper. `ivm` only exposes the workflow above; arbitrary
  incus features are reached with `incus` directly (and `ivm list` / `ivm top`
  are explicit raw passthroughs for that reason).
- NOT a guest-side configuration manager. No ansible/python is required in the
  guest; "share my dotfiles/emacs.d" happens via host-side dotfiles staging, not
  by running roles inside the VM.
- NOT multi-host / clustering. One local incus host.
- NOT a container tool. VMs only (full kernel); see
  [`docs/incus-vs-podman.md`](docs/incus-vs-podman.md).

## 2. CLI contract

`ivm <subcommand> [args]`. Bare `ivm` (no args) MUST print full help and exit 0.

**Global flags** (before the subcommand):

| Flag | Effect |
|---|---|
| `--dry-run` | print every MUTATING incus command instead of running it; read-only probes still run. |
| `-y` / `--yes` | skip every confirmation prompt and the `init` name prompt (use the default name). |
| `--name <vm>` | target this existing VM by instance name, ignoring the cwd binding. Applies to the VM-acting subcommands; NOT to `init` / `env` / `list`. |
| `--root <dir>` | ivm install root (schema + templates + fcitx5 script). Default `~/.local/share/ansible-managed/vm-incus/ivm` (env `IVM_ROOT`). |
| `--shared-assets-root <dir>` | shared provision-asset cache; rarely overridden (env `SHARED_PREBUILT_PROVISION_ASSETS_ROOT`). |

**Exit codes.** `0` success · `1` `ivm` error (any `die()`) · `2` argparse usage
error (bad/missing args) · `130` Ctrl-C (prints `ivm: aborted`, no traceback).

**VM resolution.** Every VM-acting subcommand targets ONE VM, in this precedence:
an EXPLICIT name wins over the cwd binding. Explicit = the global `--name <vm>`,
OR - for a subcommand that takes no positional of its own (`shell*` / `start` /
`stop` / `reboot` / `delete` / `update` / `overwrite-dotfiles` / `gui` / `info` /
`resize`) - a trailing `<vm>` positional (`ivm stop foo`), a shortcut for `--name`.
Giving BOTH `--name` and a positional that DISAGREE MUST error (no silent pick).
With neither, the VM is the one whose `user.ivm_host_bound_dir` tag matches the
current directory (or a parent dir, offered interactively). `user.ivm_init_at_dir`
is a pure HISTORICAL record (where `ivm init` ran; also the managed-VM marker) and
MUST NOT drive resolution. Subcommands that DO take a positional (`provision` /
`push` / `mount` / `snapshot` / `expose` / `unexpose`) target a VM only by cwd or
`--name`. `rename` is special: its LAST positional is the NEW name, and the target
may be given as an optional LEADING positional (`ivm rename [<old-vm>] <new-name>`,
the `incus rename` order) - it MUST participate in the same `--name`-vs-positional
conflict check. `restore` is the other special case: its own positional
(`<file>|latest`) comes FIRST and an optional trailing `<vm>` follows (`ivm restore
latest <vm>`) - unambiguous because a lone arg is always the restore target; it
MUST join the same conflict check. `adopt` is the one exception - it MUST require
`--name` (the VM has no tags yet).

The binding tag has two states - NO sentinel value, because every read path
(`incus list` CSV columns, `incus config get`) returns "" for an absent tag
anyway, so "empty" and "absent" are indistinguishable by design: a real dir =
bound; no tag = unbound (a `host_bound_dir: ""` template, `ivm unset
host-bound-dir`, or a legacy pre-tag VM). Unbound VMs NEVER take part in
cwd/ancestor matching and are NEVER auto-picked as a fallback - explicit name
only. The no-match error MUST list them with a copyable next command
(name-targeting; plus the `ivm set host-bound-dir` one-liner for any whose
recorded `user.ivm_init_at_dir` matches the cwd or an ancestor - typically a
legacy VM init'd right there), and `cd` MUST refuse them.

### 2a. VM-acting subcommands (resolve by cwd, `--name`, or a trailing `<vm>`)

The canonical list is the `CWD_RESOLVED` table in `files/ivm`; one-line help is
`CWD_RESOLVED_HELP`; handlers are `CWD_RESOLVED_HANDLER`. These three MUST stay
key-aligned.

| Subcommand (aliases) | Args | Behavior | Confirms? |
|---|---|---|---|
| `shell` / `shell-user` (`sh` / `sh-user`) | - | zsh into the VM as `user`; start it if stopped. Start dir = `shell_default_dir_after_login` when set + present, else home. | no |
| `shell-root` (`sh-root`) | - | zsh into the VM as `root`. | no |
| `start` | - | start the VM, wait until ready (no-op if running). | no |
| `stop` | `[--force]` | stop the VM (disk state preserved). `--force` => `incus stop --force`: no clean guest shutdown, incus SIGKILLs the qemu process (unflushed guest writes lost). | yes |
| `reboot` | `[--force]` | `incus restart` the VM. `--force` => `incus restart --force`: SIGKILL, then start. | yes |
| `delete` | - | delete the VM + disk + snapshots + its dir binding. | yes |
| `rename` | `[<old-vm>] <new-name>` | rename the VM (`incus rename`; the optional leading `<old-vm>` mirrors incus's argument order). MUST refuse a running VM (incus renames stopped instances only) and MUST re-apply the init-time name checks to the new name (valid incus name, not taken, virtiofs socket paths still fit `sun_path`). Snapshots + binding tags travel with the instance. | yes |
| `update` | - | refresh + upgrade all guest packages (apt/zypper/dnf per family). | no |
| `provision` | `[unit ...]` | install distro bundle(s) / thirdparty recipe(s) / dotfiles feature(s) onto an existing VM. NO units => LIST all installable units + descriptions (needs no VM). | no |
| `resize` | `--cpu N` / `--memory SIZE` / `--disk SIZE` | change an existing VM's vCPU / RAM / root-disk. cpu+memory apply live; disk GROWS only (MUST refuse shrink) and resizes only the host block device. A SIZE is a number + unit - `16G`, `1.2GB`, `512MiB`; bare `G`/`M`/`K`/`T` are IEC, and ivm re-renders into the whole-number unit incus accepts (`1.2GB` -> `1200MB`). | no |
| `mount` | `ls` \| `attach <host> <guest> [--ro] [--shadow SUB ...]` \| `shadow <guest_path>` \| `detach <target>` | inspect / change virtio-fs shares after init (hotplugged). `detach` PRINTS what it will unbind (`device: host-source -> guest-path`, incl. dragged shadow masks) + CONFIRMS; unbinds only - host data is NEVER deleted. | `detach` |
| `push` | `<local> <guest> [--as-root]` | copy a host file/dir into the VM (`incus file push`). Owns as `user` (1000) unless `--as-root`. | no |
| `snapshot` | `[create\|list\|restore\|delete\|rename\|show] [name]` | `incus snapshot` wrapper, VM filled in. | no |
| `gui` | - | open a SPICE graphical console, detached from the shell. | no |
| `info` | - | print the VM's live state, GROUPED: Basic (status/created/last-started/template/image/hw/snapshots/host-bound-dir/guest-shell-dir/user-sudo), Network (ip, services, bridge, ssh-server, forwards), Mounts, Storage, Usage (the template's `usage:` notes, read LIVE from the template file via `user.ivm_template`). `last started` = same start-only semantics as `list`'s Up/Last-On. Read-only. | no |
| `expose` | `[<port>\|<host>:<guest>]` | forward a host TCP port to the VM so the LAN can reach a service in it (pins the VM's IPv4 first). Host listen address MUST follow the incus daemon version: `0.0.0.0` on >= 7.2, else the host's default-route IPv4 (older daemons reject a wildcard in `nat=true` mode, and a VM proxy has no non-NAT mode). NO arg => LIST current forwards. | no |
| `unexpose` | `[<host-port>\|--all]` | remove a forward: `<host-port>` => that one; `--all` => ALL of this VM's forwards, PRINTED before the prompt. The two MUST be mutually exclusive. NO arg => remove NOTHING: print the usage + LIST current forwards (the passable host ports). MUST NOT reuse the stop/reboot live-session warning - removing a proxy device never touches `incus exec` sessions. | yes (`--all`) |
| `backup` | - | tar the app data the VM's template `backup:` block names (`paths` inside `dir`) out of the guest into `<host XDG Download>/<host_downloads_subdir>/<vm>_<YYYYMMDD_HHMM>.tar`, streamed over `incus exec` as `user` (inside `podman unshare` when declared). MUST stop the block's per-user `unit` first and start it again after (only if it was running); a failed tar MUST remove the partial file. Read LIVE from the template (via `user.ivm_template`) - never from anything baked into the guest - so a template fix reaches every existing VM. Dies naming the missing link (no tag / no template file / no `backup:` block). | no |
| `restore` | `[<file>\|latest] [<vm>]` | the reverse: stop the unit, `tar --extract` the tar inside `dir` (same `user` / `podman unshare` path), start the unit (unconditionally). `latest` = the newest `*.tar` in the VM's backup dir (the old in-guest `llm-backup` tars included); a bare filename is looked up there. Files in the tar overwrite the guest's; files only in the guest stay. MUST print what it overwrites + CONFIRM before touching the VM (`--yes` skips). NO target => restore NOTHING: list this VM's backups newest first + the copyable command. | yes |
| `overwrite-dotfiles` | - | re-push the host-staged dotfiles into the VM (no re-provision). | no |

`info` MUST print EVERY field on EVERY run, with an explicit placeholder
(`(none)`, `(unset - ...)`) when empty - never omit a row.

`stop` / `reboot` / `delete` MUST, before their confirm prompt, LOUDLY warn when the
guest has live interactive sessions (each an `ivm shell` / console / SSH login) the
action would kill - detected best-effort by asking the guest for pty-owning processes
(`ps -eo tty=`); a stopped / unreachable VM just warns nothing.

`stop --force` / `reboot --force` MUST additionally warn that the guest gets no clean
shutdown before the same prompt. They exist for incus `Error` status - qemu still
running but incusd cannot reach its QMP monitor - where incus refuses a clean shutdown
("The instance cannot be cleanly shutdown as in Error status") and only a SIGKILL
clears it. So `stop --force` MUST NOT take the "already stopped" no-op shortcut on a
non-`stopped` VM (`error`, `frozen`): those still have a process to kill.

WITHOUT `--force`, `start` / `stop` / `reboot` MUST detect `error` up front and die
naming `ivm reboot --force <vm>`. They MUST NOT run the incus call that cannot succeed
(`incus start` / `incus restart`, which fail with "The instance cannot be started as in
Error status" / "...cleanly shutdown as in Error status"), and `stop` MUST NOT report an
`error` VM as "already stopped" - qemu is alive, and that message sends the reader away
from the only command that clears the state.

### 2b. Non-VM subcommands (resolve no VM)

| Subcommand | Args | Behavior |
|---|---|---|
| `init` | `[template] [name]` | create a VM from `<template>`, writing `user.ivm_host_bound_dir` from the template's REQUIRED `host_bound_dir` field (host-expanded: `$(pwd)` = the cwd; `""` = unbound, NO tag written, default name drops the path suffix). Prompt for the name (default `<template>-<bound-dir-path>`, editable) unless `name` given or `--yes`; confirm before creating. NO `template` => LIST all templates + descriptions. |
| `env` | `<template>` | load + validate a template, print its resolved config (incl. the flattened package list). |
| `list` (`ls`) | `[incus args]` | NO arg => table of ivm-MANAGED VMs (those tagged `user.ivm_init_at_dir`): State, Name, MEM(guest), MEM(host), Disk, Created, Up/Last-On, Host-Bound Dir (labelled placeholder when unbound/legacy), IPv4. `Created` = incus `created_at` as local date + age. `Up/Last-On` = running/frozen -> `up 3d 4h` since this boot (`state.started_at`, fallback `last_used_at`); stopped -> `last on 19d ago` = the last START (incus records starts only, never a stop time); `(never started)` labelled. `MEM(guest)` = incus guest-agent memory; `MEM(host)` = qemu process host RSS (the true cost the guest figure under-reports; see `top`); `Disk` = guest root-fs USED, read live per running VM via `incus exec <vm> -- df -Pk /` (reliable, vs incus's sporadic VM disk metric lxc/incus#259; guest-fs used, can trail the host `root.img` btrfs footprint until `fstrim`). Non-running VMs show `(<state>)`; an unreadable running figure shows `-`. ANY arg => raw `incus list` passthrough of ALL instances (e.g. `ivm list --format csv`). |
| `cd` | `[<vm>]` | print a VM's host-bound dir (`user.ivm_host_bound_dir`) to stdout, for the `ivm()` shell wrapper (`files/shell-init/ivm.sh`) to `cd` into - a child process can't change the parent shell's cwd. Resolves the VM by NAME (the INVERSE of cwd resolution; no `--name`). NO arg => list managed VMs + dirs on STDERR (stdout stays empty, so the wrapper cd's nowhere). Completes VM names -> their dirs. An unbound (sentinel) or legacy (tag absent) VM MUST be refused (non-zero exit, empty stdout) - it has no dir to jump to. |
| `top` | `[incus args]` | raw `incus top` passthrough (live per-instance CPU/mem/disk). |
| `adopt` | (`--name` required) | bring an unmanaged VM (hand-made / older-ivm) under ivm management. |
| `storage-status` | `[--json]` | show the host `default` storage pool status (driver, loop file, mount, fstab, verdict). |

### 2c. `set` / `unset <aspect>` (guest settings)

A two-level namespace (verb then aspect), NOT a generic key=value setter. The
aspect registry is `SET_UNSET_ASPECTS` in `files/ivm`; every aspect MUST have
BOTH `set` and `unset` (full symmetry). Bare `ivm set` / `ivm unset` (no aspect)
MUST list the aspects + descriptions (needs no VM).

| Aspect | `set` args | `set` does | `unset` does |
|---|---|---|---|
| `password` | `<username>` | set that guest account's login password (prompted, sent via stdin). | lock the account's password. |
| `ssh-server` | `<username> [--pubkey FILE ...]` | authorize key-based SSH for the account (append keys, default `~/.ssh/id_ed25519.pub`; ensure sshd up; `root` also gets `PermitRootLogin prohibit-password`). | revoke the key(s) (and root's override); leave sshd running. |
| `guest-shell-dir` | `<path>` | set the GUEST dir `ivm sh` starts in, inside the VM (`user.ivm_shell_default_dir_after_login`). `<path>` is an absolute GUEST path; need not exist yet. | clear it (revert to incus's default cwd). |
| `host-bound-dir` | `[<path>]` | bind the VM to a HOST dir for cwd resolution (`user.ivm_host_bound_dir`); no path = the current dir. Also the legacy-VM migration path. | unbind: remove the tag (name-only targeting). |
| `user-sudo` | - | let `user` sudo, gated by ROOT's password (`Defaults:user rootpw`); needs `set password root` first. | remove the sudoers drop-in. |
| `git-ssh-key` | `<keyfile> [--host HOST]` | copy a host PRIVATE ssh key into the VM (renamed to its type's default name so ssh auto-uses it), trust each `--host` (default github.com), and set git `insteadOf` to rewrite https->ssh - so in-guest git / `go get` reach private repos. MUST warn + require typing `yes i know` (not skippable by `--yes`; refuses with no TTY); records the pushed key name in `user.ivm_git_ssh_key_name`. | remove that recorded key + the `insteadOf` rewrite. |
| `static-ip` | - | pin the VM's IPv4 to its CURRENT DHCP lease (eth0 `ipv4.address` - the same pin `expose` makes implicitly; same address, so no reboot). Needs the VM running with a lease. `info`'s Network `ip` row MUST label static vs dynamic. | unpin - back to a dynamic lease. MUST refuse while `expose` forwards exist (their proxy devices target the pinned address). |

### 2d. Completions drift risk

zsh `files/completions/_ivm` and bash `files/completions/ivm.bash` are
HAND-MAINTAINED, NOT generated from the tables above. Any change to the
subcommand set, an aspect, or an arg MUST update both completion files in the
same change. (Their DATA may read the rendered JSON / templates dynamically, but
the per-case DISPLAY wiring is manual.) VM-name completion (the `--name` value and
the trailing `<vm>` on no-positional subcommands) MUST, in zsh, show a dir
description for EVERY managed VM: the bound dir (`user.ivm_host_bound_dir`) when
bound, else the labelled `(unbound; init dir <user.ivm_init_at_dir>)` fallback -
a managed VM's dir column must never silently vanish. Only a hand-made instance
(no ivm tags) completes as a bare name. `cd` offers only VMs with a REAL bound
dir (`ivm cd` refuses the rest). bash lists names only.

## 3. Template schema

Templates are YAML at `<root>/templates/<name>.yaml`, validated against
`files/template.schema.json` (JSON Schema draft 2020-12,
`additionalProperties: false`). That file is the authoritative field list; this
is the summary.

| Block | Keys (summary) |
|---|---|
| `template_name`, `description` | id (REQUIRED) + one-line summary for the `init` listing. |
| `os` (REQUIRED) | `type` (`linux`/`windows`), `distro` (linux only: debian/ubuntu/opensuse/fedora), `image.{source,uri}`. |
| `hw` | `cpu`, `memory` (`8G`), `disk` (`30G`), `secureboot`, `tpm`, `nested_virt` (host-gated). |
| `sys` | `gui`, `input_method`, `timezone`, `tmpfs[]`, `ssh_server.{enabled,port,root_login,password_login,authorized_keys}`. |
| `net` | `mode` (`nat`/`macvlan`/`bridge`), `parent`. |
| `mounts[]` | `host`, `guest`, `ro`, `shadow[]` (subpaths to mask). Applied ONLY at init. |
| `shell_default_dir_after_login` | initial cwd for `ivm shell`; host-expanded at init like a mount `guest` (`/workspaces/$(basename "$(pwd)")` OK), stored as `user.ivm_shell_default_dir_after_login` (`ivm set guest-shell-dir` changes it later). |
| `host_bound_dir` | REQUIRED. The host dir the VM binds to for cwd resolution, written to `user.ivm_host_bound_dir` at init (`user.ivm_init_at_dir` separately records the init dir as history). Host-expanded like a mount `host` (`$(pwd)` = the init cwd - project boxes; relative results made absolute). `""` = unbound appliance (the `llm_*` templates; must be the explicit `""` - a bare key is YAML null and is rejected): NO tag written, never resolves by cwd (name-only targeting; `cd` refuses it + drops out of `cd` completion; `ivm set host-bound-dir` binds later), default instance name `ivm-<template_name>` with no path suffix. |
| `services` | host-reachable endpoints as `name: port` (lowercase names; ports 1-65535). An ANNOTATION of what `post_install_script` sets up, not an input to it: `init` MUST warn when a declared port's literal is absent from the script (stale-declaration tripwire), writes the `user.ivm_services` tag (`name:port` comma-joined, sorted), and every surface prints ONE format `name=<host>:<port>`: `info` (live IP or empty host part - the neighbouring ip row explains), the init confirm preview (`<guest-ip>` stand-in), the init ready message (live IP - the moment the address is wanted), plus `env` (raw `name:port`). `(none declared)` when absent. Declare only HOST-reachable endpoints (llm_librechat lists the web UI, not the compose-internal mongo). |
| `usage` | post-init how-to notes, one short line each (set an API key, default account, where backups land). Shown by `info` (Usage group); read LIVE from the template file (resolved via `user.ivm_template`, NOT stamped into VM config) so template edits update existing VMs' `info`. Placeholders when the tag / file / field is missing - the group itself always prints. Optional. |
| `backup` | what `backup` / `restore` operate on: `unit` (per-user systemd unit stopped around the tar), `dir` (absolute guest dir tar runs in), `paths[]` (relative to `dir`; every entry must exist), `podman_unshare` (wrap tar for rootless-podman-owned data), `host_downloads_subdir` (subdir of the host XDG DOWNLOAD dir the tars land in). Read LIVE like `usage`. Optional - without it both commands refuse, naming the block. |
| linux provisioning | `distro_package_groups[]`, `distro_packages[]`, `thirdparty_software[]`, `post_install_script`. Dotfiles are NOT a template field: the baseline set is pushed to every VM, anything else via `ivm provision <feature>`. |
| `windows` | `unattend`, `post_install_powershell`. |

**Two-tier rule (schema-enforced).** `os.type: linux` REQUIRES `os.distro` and
forbids the `windows` block. `os.type: windows` forbids `os.distro` and ALL the
linux provisioning fields (they do not apply); provisioning comes from the
`windows` block.

## 4. Invariants

These MUST hold for every VM `ivm` creates or touches.

- **Instance name.** Matches `INCUS_NAME_RE` (`^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$`):
  starts alphanumeric, then `[a-zA-Z0-9-]`, max `MAX_NAME_LEN` = 63 chars. A
  valid name is NOT sufficient: each mount's virtio-fs socket path
  (`/var/lib/incus/devices/<project_>?<instance>/virtio-fs.<device>.sock`) MUST
  fit `AF_UNIX`'s `sun_path` (`SUN_PATH_MAX` = 108 bytes incl. NUL). `ivm` MUST
  reject an over-long name at pick time, counting the project prefix
  (`user-<uid>_`) and the longest device suffix - otherwise `incus start` dies
  with a cryptic `connect: invalid argument`.
- **Project model.** Unprivileged `incus`-group users operate in the per-user
  RESTRICTED project `user-<uid>`, NEVER `default`. Consequence: `incus exec` /
  `incus restart` etc. take NO sudo (sudo => root => `default` => "instance not
  found"); only `incus network show` and `firewall-cmd` need sudo.
- **Network model.** A VM's `eth0` attaches to the standard managed bridge
  `incusbr0` (IPv4 NAT + DNS), NOT the flaky per-user `incusbr-<uid>` that incus
  auto-creates. The host-install role repoints the `user-<uid>` project's default
  profile `eth0` onto `incusbr0`.
- **Home namespace.** Everything `ivm` deploys for the role lives under the one
  subdir `~/.local/share/ansible-managed/vm-incus/`. Uninstall = `rm -rf` that
  subdir. The SHARED provision-asset cache
  (`~/.local/share/ansible-managed/shared-prebuilt-provision-assets/`) is a
  separate, regenerable dir co-owned with `qvm`/`pvm`.
- **Readiness contract (`wait_ready`).** After `init`/`start`, `ivm` MUST block
  until the guest is provisionable: (1) the agent answers `incus exec`, THEN
  (2) the network is online = an IPv4 default route EXISTS and DNS resolves. A
  guest with only an IPv6 SLAAC address (kernel-side, ungated) is NOT ready - on
  that signature `ivm` MUST name the likely host firewall DHCP drop and print the
  fix, never auto-`sudo` it.
- **`ansible_os_family` is derived, never specified.** It comes from `os.distro`
  via `DISTRO_TO_ANSIBLE_OS_FAMILY` and keys both the dotfiles staging and the
  package-group overlays.
- **The `~/.centralized-lang-pkgs` env file precedes recipes.** Every guest gets
  `centralized-lang-pkgs.env.sh` as a BASELINE dotfiles feature
  (`centralize-lang-pkgs-dir`, staged from `roles/centralize_lang_pkgs_dir` - the
  npm/pip/pipx/cargo/go global-install redirect, same tree as the host). Thirdparty
  recipes source it at install time, so it MUST be in the guest before any recipe
  runs: `init` inlines the staged file into the provision script right after `user`
  exists (the baseline dotfiles push happens only AFTER recipes, on purpose);
  `provision` re-pushes the feature before running recipes; `overwrite-dotfiles`
  re-pushes it with the rest of the baseline.

## 5. Host prerequisites

The host-install path (`make vm-incus-install`, role `tasks/incus_host_install.yml`)
MUST provide:

- **incus daemon** installed + enabled, with `incus-user.socket` up.
- **`incus` group** membership for the user (the lower-privilege group than
  `incus-admin`; the client auto-detects `unix.socket.user`).
- **Storage pool** `default` (first-time `incus admin init --preseed` only; an
  existing pool is NEVER re-pointed). Default backend `btrfs` on a loop file at
  `/home/incus-storage.img`; overridable (`dir`/`btrfs`/`zfs`/`lvm-thin`). See
  [`docs/incus-host-setup.md`](docs/incus-host-setup.md).
- **`incusbr0`** managed bridge (IPv4 NAT + DNS), with the `user-<uid>` project
  routed onto it.
- **firewalld hosts only:** `incusbr0` bound to the built-in `trusted` zone, in
  BOTH runtime and permanent config - otherwise the default `public` zone DROPs
  DHCP (udp/67) and guests get IPv6 but no IPv4 lease.
- **proxy devices** allowed in the `user-<uid>` project (default on) so `ivm
  expose` can forward host ports; set `vm_incus_allow_proxy_devices: false` on a
  shared/multi-user host.

Hosts: Debian / openSUSE / Fedora families. Target guests are usually VMs, so
nested-virt features stay opt-in.
