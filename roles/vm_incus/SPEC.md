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

**VM resolution.** Every VM-acting subcommand targets ONE VM: `--name <vm>` if
given, else the VM whose `user.ivm_init_at_dir` tag matches the current directory
(or a parent dir, offered interactively). `adopt` is the one exception - it MUST
require `--name` (the VM has no binding yet).

### 2a. VM-acting subcommands (resolve by cwd or `--name`)

The canonical list is the `CWD_RESOLVED` table in `files/ivm`; one-line help is
`CWD_RESOLVED_HELP`; handlers are `CWD_RESOLVED_HANDLER`. These three MUST stay
key-aligned.

| Subcommand (aliases) | Args | Behavior | Confirms? |
|---|---|---|---|
| `shell` / `shell-user` (`sh` / `sh-user`) | - | zsh into the VM as `user`; start it if stopped. Start dir = `shell_default_dir_after_login` when set + present, else home. | no |
| `shell-root` (`sh-root`) | - | zsh into the VM as `root`. | no |
| `start` | - | start the VM, wait until ready (no-op if running). | no |
| `stop` | - | stop the VM (disk state preserved). | yes |
| `reboot` | - | `incus restart` the VM. | yes |
| `delete` | - | delete the VM + disk + snapshots + its dir binding. | yes |
| `update` | - | refresh + upgrade all guest packages (apt/zypper/dnf per family). | no |
| `provision` | `[unit ...]` | install distro bundle(s) / thirdparty recipe(s) / dotfiles feature(s) onto an existing VM. NO units => LIST all installable units + descriptions (needs no VM). | no |
| `resize` | `--cpu N` / `--memory NG` / `--disk NG` | change an existing VM's vCPU / RAM / root-disk. cpu+memory apply live; disk GROWS only (MUST refuse shrink) and resizes only the host block device. | no |
| `mount` | `ls` \| `attach <host> <guest> [--ro] [--shadow SUB ...]` \| `shadow <guest_path>` \| `detach <target>` | inspect / change virtio-fs shares after init (hotplugged). `detach` unbinds only - host data is NEVER deleted. | no |
| `push` | `<local> <guest> [--as-root]` | copy a host file/dir into the VM (`incus file push`). Owns as `user` (1000) unless `--as-root`. | no |
| `snapshot` | `[create\|list\|restore\|delete\|rename\|show] [name]` | `incus snapshot` wrapper, VM filled in. | no |
| `gui` | - | open a SPICE graphical console, detached from the shell. | no |
| `info` | - | print the VM's live state, GROUPED: Basic (status/image/hw/snapshots/shell-dir/user-sudo), Network (ip, bridge, ssh-server, forwards), Mounts, Storage. Read-only. | no |
| `expose` | `[<port>\|<host>:<guest>]` | forward a host TCP port to the VM so the LAN can reach a service in it (pins the VM's IPv4 first). NO arg => LIST current forwards. | no |
| `unexpose` | `[<host-port>]` | remove a forward. NO arg => remove ALL of this VM's forwards. | yes (no-arg form) |
| `overwrite-dotfiles` | - | re-push the host-staged dotfiles into the VM (no re-provision). | no |

`info` MUST print EVERY field on EVERY run, with an explicit placeholder
(`(none)`, `(unset - ...)`) when empty - never omit a row.

### 2b. Non-VM subcommands (resolve no VM)

| Subcommand | Args | Behavior |
|---|---|---|
| `init` | `[template] [name]` | create a VM from `<template>`, bind it to the cwd. Prompt for the name (default `<template>-<cwd-path>`, editable) unless `name` given or `--yes`; confirm before creating. NO `template` => LIST all templates + descriptions. |
| `env` | `<template>` | load + validate a template, print its resolved config (incl. the flattened package list). |
| `list` | `[incus args]` | NO arg => table of ivm-MANAGED VMs (those tagged `user.ivm_init_at_dir`): State, Name, Working Directory, IPv4. ANY arg => raw `incus list` passthrough of ALL instances (e.g. `ivm list --format csv`). |
| `cd` | `[<vm>]` | print a VM's working-dir root (`user.ivm_init_at_dir`) to stdout, for the `ivm()` shell wrapper (`files/shell-init/ivm.sh`) to `cd` into - a child process can't change the parent shell's cwd. Resolves the VM by NAME (the INVERSE of cwd resolution; no `--name`). NO arg => list managed VMs + dirs on STDERR (stdout stays empty, so the wrapper cd's nowhere). Completes VM names -> their dirs. |
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
| `shell-dir` | `<path>` | set the dir `ivm sh` starts in (`user.ivm_shell_default_dir_after_login`). `<path>` is an absolute GUEST path; need not exist yet. | clear it (revert to incus's default cwd). |
| `user-sudo` | - | let `user` sudo, gated by ROOT's password (`Defaults:user rootpw`); needs `set password root` first. | remove the sudoers drop-in. |
| `git-ssh-key` | `<keyfile> [--host HOST]` | copy a host PRIVATE ssh key into the VM (renamed to its type's default name so ssh auto-uses it), trust each `--host` (default github.com), and set git `insteadOf` to rewrite https->ssh - so in-guest git / `go get` reach private repos. MUST warn + require typing `yes i know` (not skippable by `--yes`; refuses with no TTY); records the pushed key name in `user.ivm_git_ssh_key_name`. | remove that recorded key + the `insteadOf` rewrite. |

### 2d. Completions drift risk

zsh `files/completions/_ivm` and bash `files/completions/ivm.bash` are
HAND-MAINTAINED, NOT generated from the tables above. Any change to the
subcommand set, an aspect, or an arg MUST update both completion files in the
same change. (Their DATA may read the rendered JSON / templates dynamically, but
the per-case DISPLAY wiring is manual.)

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
| `shell_default_dir_after_login` | initial cwd for `ivm shell`. |
| linux provisioning | `distro_package_groups[]`, `distro_packages[]`, `thirdparty_software[]`, `dotfiles[]`, `post_install_script`. |
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
