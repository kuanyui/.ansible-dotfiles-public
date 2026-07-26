# ivm DESIGN (architecture)

How and why `ivm` is built. Pairs with [`SPEC.md`](SPEC.md) (the WHAT contract)
and [`README.md`](README.md) (usage). The design rationale and the rejected
alternatives that led here are in
[`docs/redesign-history.md`](docs/redesign-history.md) (a historical log - this
file is the current state).

`ivm` is ONE Python script, `files/ivm` (~2950 lines, stdlib + lazy
`yaml`/`jsonschema`). One launcher manages both general workstation VMs and
coding-agent VMs: there is NO `agent` abstraction - a "claude" VM is just a
template whose `post_install_script` installs Claude Code.

## 1. Host-side provisioning (no ansible/python in the guest)

The defining choice: the guest gets ZERO ansible and ZERO python (unless the VM
itself installs them). `ivm` runs on the HOST and drives incus via `incus exec`.
Embedding ansible-core would force python into every guest, even a minimal one
the user wants kept tiny.

`init` sequence:

```
incus create (stopped)
  -> attach devices: mounts (+ shadow masks), hw.tpm, macvlan/bridge nic
  -> incus start -> wait_ready
  -> provision via incus exec: native pkg mgr (apt/zypper/dnf) installs
     baseline + distro_package_groups + distro_packages; set timezone/tmpfs;
     create `user`; chsh both to zsh; configure sshd; run post_install_script
     as root (drops to `user` via `su - user -c` for user-scoped bits)
  -> push the host-staged user/root dotfiles (incus file push)
```

"Share the project's emacs.d" therefore happens by STAGING dotfiles host-side and
pushing them, never by running a role in the VM.

## 2. Metadata-driven argparse - the "edit these together" map

A few module-level tables describe the subcommands; `build_parser()` and `main()`
LOOP/branch over them rather than hard-coding each. To add or change a subcommand
you edit the tables in lockstep - this map is the whole architecture:

| Table (in `files/ivm`) | Holds | Must stay aligned with |
|---|---|---|
| `CWD_RESOLVED` | the VM-acting subcommand names (resolve by cwd / `--name`) | `CWD_RESOLVED_HELP`, `CWD_RESOLVED_HANDLER` |
| `CWD_RESOLVED_HELP` | one-line `--help` per such subcommand | keys == `CWD_RESOLVED` |
| `CWD_RESOLVED_HANDLER` | name -> `cmd_*` function | keys == `CWD_RESOLVED` |
| `CWD_RESOLVED_ALIASES` / `SUBCOMMAND_ALIAS_TO_CANONICAL` | short aliases (`sh`->`shell`) + fold-back | both derived from the first |
| `SET_UNSET_ASPECTS` | aspect -> (`set` help, `unset` help) | drives parser + bare-listing + dispatch |

- **`build_parser()`** adds the special subcommands (`init`/`env`/`list`/`top`/
  `adopt`/`storage-status`, and the `set`/`unset` and `mount` TWO-LEVEL trees) by
  hand, then loops `for name in CWD_RESOLVED` adding per-subcommand args in
  `if name == ...` blocks. `mount` and `set`/`unset` are the nested-subparser
  models to copy.
- **`main()`** parses, folds aliases, EARLY-RETURNS the subcommands that resolve
  no VM (`list`/`top`/`init`/`env`/`adopt`/`storage-status`, bare `provision`,
  bare `set`/`unset`), THEN resolves the target VM, THEN dispatches by
  `(subcommand[, aspect])`.
- **Completions are NOT generated from these tables** - `files/completions/_ivm`
  (zsh) and `files/completions/ivm.bash` (bash) are hand-kept and MUST be edited
  alongside any table change (see SPEC §2d). This hand-kept gap is the known
  drift risk.

## 3. Key mechanisms

- **`wait_ready`** - two phases: block until the agent answers `incus exec`
  (90 s), THEN until the network is online = IPv4 default route + DNS (60 s). On
  network-timeout it prints a filled-in copy/paste diagnostics block (real VM
  name + resolved bridge, correct sudo / no-sudo split), and if the guest shows a
  global IPv6 but no IPv4 default route it leads with the firewalld DHCP-drop
  cause. It DETECTS + INSTRUCTS only; it never `sudo`s (it talks to incus
  unprivileged via the socket).
- **Shadow masks** - to hide a subpath from the guest (e.g. an agent VM must not
  see a mounted project's `.git`/`.env`), `ivm` attaches an EMPTY read-only incus
  disk device at that guest path, masking whatever the real mount exposes there.
  Directories only - a VM disk device cannot mask a single file. `detach` drops
  the masks too; host data is never touched.
- **cwd -> VM resolution** - `init` tags the VM `user.ivm_init_at_dir=<cwd>`. The
  VM-acting subcommands look up the VM whose tag matches the current dir; run from
  a SUBDIR and `ivm` offers the nearest ancestor's VM; when several VMs share one
  dir it shows a TTY picker (or dies asking for `--name` with no TTY). Resolution
  is by the tag, not the free-form instance name. Appliance templates
  (`cwd_bound: false`, e.g. the `llm_*` family) store the `__CWD_UNBOUND__`
  sentinel instead: the tag keeps marking the VM as managed, but it never joins
  cwd/ancestor matching and is never auto-picked - name-only targeting, so a
  stray `ivm stop` in some dir can never hit an appliance. The no-match error
  lists these global VMs so the copyable next command is right there.
- **Shared prebuilt provision assets** - the package-group / thirdparty install
  data and the dotfiles tree are NOT computed in the guest. The internal producer
  role `roles/_shared_prebuilt_provision_assets` renders, host-side, a REGENERABLE
  cache: `distro-package-groups.json` + `thirdparty-software.json` + a
  feature-first `dotfiles/<feature>/{__common__,<family>}/...` tree, under
  `~/.local/share/ansible-managed/shared-prebuilt-provision-assets/`. `ivm` reads
  it; `qvm`/`pvm` will read the SAME cache (hence the `ivm`-free name). Adding a
  bundle/recipe requires its key in that role's render dict - the one hand-kept
  feature list.
- **Storage-pool inspector** - `files/incus_storage_pool.py` builds the host's
  `incus admin init` preseed AND reports pool status (driver, loop file, mount,
  fstab, verdict). `ivm storage-status` runs the SAME inspector the host-install
  role uses, so the launcher and the installer never disagree about storage.
- **`expose` IPv4 pin** - `expose` adds an incus proxy device (`nat=true`) so the
  LAN can reach `<host-ip>:<port>` and incus forwards it into the VM. The proxy
  needs a STATIC target, so `expose` first pins the VM's IPv4 to its current lease
  (no reboot). host<->VM already works over incusbr0 NAT; this only ADDS the LAN
  path.

## 4. Why `incusbr0`, not the per-user `incusbr-<uid>`

incus auto-creates a per-user bridge (`incusbr-<uid>`, e.g. `incusbr-1000`) for
the `user-<uid>` restricted project, but it is flaky - it can come up with no
IPv4. So the host-install role repoints the project's default-profile `eth0` onto
the standard, well-tested `incusbr0` (IPv4 NAT + DNS); `incusbr-<uid>` lingers
unused. The VMs do NOT use it.

**firewalld dependency.** firewalld matches a zone PER INTERFACE. On firewalld
hosts `incusbr0` MUST be bound to the built-in `trusted` zone (the host-install
role does this, in both runtime and permanent config); otherwise it falls to the
default `public` zone, which DROPs DHCP (udp/67), so guests get an IPv6 SLAAC
address but never an IPv4 lease. Binding only `incusbr0` leaves the host's real
NICs in `public` - the trust is scoped to the one internal NAT bridge. This is
the host-side counterpart to `wait_ready`'s detect-and-instruct (SPEC §4). Full
incident write-up: the role `TODO.md` network-incident log (top) and
[`docs/incus-host-setup.md`](docs/incus-host-setup.md).
