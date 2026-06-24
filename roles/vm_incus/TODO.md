# roles/vm_incus TODO

Durable, role-local notes (same convention as the repo-root TODO.md).
Status: `[ ]` pending · `[~]` in progress · `[x]` done

## 2026-06-24 network incident - diagnosis log + decisions (READ FIRST if debugging ivm networking)

**Symptom.** After a HOST REBOOT, all 5 `user-1000` VMs showed `RUNNING` in `incus list` but had
NO IPv4 (empty IPv4 column; IPv6 only). `ivm sh` failed with "has no network connectivity after 60s
(no default route or DNS)" - `wait_ready` (ivm ~L1094) requires an IPv4 default route + DNS, and the
guests had only an IPv6 SLAAC address.

**Root cause (confirmed).** `incusbr0` was in NO firewalld zone -> fell to the default zone
(`public`) -> that zone DROPs DHCP (udp/67) on INPUT -> the guest's DHCPv4 DISCOVER never reaches
the host dnsmasq -> no IPv4 lease. IPv6 still worked because ICMPv6 RA / SLAAC is kernel-side and
permitted. Runtime fix that worked: `sudo firewall-cmd --zone=trusted --change-interface=incusbr0`
-> guest immediately leased `10.93.37.146/24`, `ivm sh` worked. Exactly the symptom the host-install
comment at `tasks/incus_host_install.yml:771-817` describes.

**Status (2026-06-24).** Fixed at RUNTIME only. The `--permanent` binding was EMPTY on this host
(the role's L803 fix never persisted here), so it WILL break again on the next reboot until the
durable fix lands. By design NOTHING should be needed after a host reboot - VMs autostart and
re-DHCP; needing a manual step IS the bug. Interim: `sudo firewall-cmd --permanent --zone=trusted
--change-interface=incusbr0 && sudo firewall-cmd --reload`, then reboot-test (feeds the firewalld PLAN).

**Decisions (settled this session):**
- **Bridge = `incusbr0`, NOT `incusbr-<uid>` (`incusbr-1000`).** incus auto-creates a per-user
  bridge for the `user-<uid>` restricted project, but it is flaky (can come up with no IPv4); the
  role repoints the project default-profile `eth0` to the standard `incusbr0`
  (`incus_host_install.yml:722-734`). `incusbr-1000` lingers as a harmless leftover (own dnsmasq);
  the VMs do NOT use it. (This is the OPPOSITE of any memory that "ivm switched to incusbr-1000".)
- **`trusted` zone is correct** (incus-upstream-recommended). firewalld matches PER-INTERFACE, so
  the host DEFAULT zone staying `public` is correct - binding only incusbr0 to trusted leaves real
  NICs in `public`. Why it works with default=`public`, why a RUNTIME-only binding is invisible in
  YaST + volatile (the runtime-vs-permanent gotcha): see `docs/incus-host-setup.md` -> Q&A
  "firewalld hosts: VMs get an IPv6 address but no IPv4".
- **ivm self-heals by DIAGNOSE+INSTRUCT, never auto-`sudo`** (it runs unprivileged via the incus
  socket; CLAUDE.md transparency rule). The durable firewall fix lives in the host-install role,
  not in ivm. -> see the two PLANs below.

**Debug GOTCHAS (save the next session hours):**
- **`incus exec` / `incus restart` take NO sudo.** They use YOUR `user-<uid>` project. `sudo incus`
  -> root -> the `default` project -> "Failed to fetch instance ... in project default: Instance not
  found". Only `firewall-cmd` and `incus network show` (managed bridge is in `default`) need sudo.
- **Non-sudo `incus network show incusbr0` prints `config: {}` even when the bridge is fully
  configured** - a restricted-project VIEW ARTIFACT (you only have use-access). Confirm the REAL
  config with `sudo incus network show incusbr0` before concluding it is broken. (This nearly sent
  us down a wrong "rebuild the bridge" path.)
- **"RUNNING but no IPv4 (IPv6 present)" - check in this order:** (1) host firewall dropping udp/67
  (firewalld zone; THIS incident), (2) guest DHCPv4 client off/misconfigured (`networkctl status`,
  `journalctl -u systemd-networkd`), (3) tap not enslaved to the bridge (`ip link show master
  incusbr0`), (4) bridge config actually wiped (`sudo incus network show`). The wait_ready PLAN
  auto-prints this block.

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

**STATUS 2026-06-24: DONE + committed.** Code `880d9fd`, completions `fd96fd4`, docs `5ff1661`.
Steps 1-7 complete. Step 8 verify - ALL GREEN: `py_compile`; CLI smoke (`ivm --help`, bare
`ivm set`/`ivm unset` aspect listing, every aspect `--help`); `bash -n` ivm.bash; `zsh -n` _ivm;
grep-zero of the 6 old verbs (only the kept `ivm-set-ssh-server.conf` filename remains, by design).
`make vm-incus-sandbox` could NOT finish in the CI/Claude env: rootless podman now BUILDS the image
(force `cgroup_manager=cgroupfs`) and STARTS the container (`netns=host`, since `pasta` is absent),
but systemd-as-PID1 never reaches ready (no systemd user session / `loginctl enable-linger` /
cgroup delegation without root). Run it on a real host for that last integration check; the direct
checks above already cover this CLI-surface change (the role's file *deployment* is unchanged).

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

**RESOLVED 2026-06-24** (per user "delete useless doc content"): `IMPLEMENTATION_PLAN.md` DELETED -
a completed build plan (all phases done), superseded by `README.md` (surface) + `REDESIGN.md`
(design) + the code + git history; its live references (ivm docstring, `cmd_stub`,
`tasks/ivm_install.yml`) were repointed/removed. `REDESIGN.md` KEPT (design rationale; ivm's
docstring points at its §8) with its stale old-verb bullet updated to `set`/`unset`. The kept
`/etc/ssh/sshd_config.d/ivm-set-ssh-server.conf` filename is an internal artifact, deliberately NOT
renamed (renaming would orphan the file on already-configured VMs). (Root `TODO.md` has 2 historical
prose mentions of the old plan path - left as-is in the user's master tracker.)

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

## `SPEC.md` + `DESIGN.md` for the role - PLAN (2026-06-24)

**Why.** Today: `README.md` (user usage) + `REDESIGN.md` (historical redesign log; ivm's
docstring points at its §8) + a ~2772-line `ivm` - but NO single normative SPEC and no clean
current-state DESIGN. Goal: one doc that says WHAT ivm must do (contract) and one that says
HOW/WHY it's built (architecture), so behavior is reviewable without reverse-engineering the script.

**Decision needed FIRST (REDESIGN.md overlap - user dislikes useless doc content).** REDESIGN.md
is already labelled "design". Proposal: `DESIGN.md` = clean CURRENT-state architecture distilled
from REDESIGN §8 "converged design" (the live design); then REDESIGN.md is either archived as
`docs/redesign-history.md` (decision log) or deleted once §8 is absorbed. Confirm before writing
to avoid a 3rd overlapping design doc.

**`SPEC.md` (normative - "what"):**
- [ ] Purpose + non-goals (host-side-provisioned incus VMs; NOT a generic incus wrapper).
- [ ] CLI contract: EVERY subcommand (init/env/list/top/adopt/storage-status; shell*/start/reboot/
  stop/delete/overwrite-dotfiles/update/provision/resize/mount/push/snapshot/gui/info/expose/
  unexpose; set/unset <aspect>) - args, behavior, confirm/dry-run/exit. Note the source-of-truth
  tables (`CWD_RESOLVED*`, `SET_UNSET_ASPECTS`, handlers) + the drift risk (completions are hand-kept).
- [ ] Template schema (point at `files/template.schema.json`; summarize field groups).
- [ ] Invariants: name rules (`INCUS_NAME_RE`, `SUN_PATH_MAX`), project model (the per-user
  `user-<uid>` RESTRICTED project, NOT `default`), network model (`eth0` -> `incusbr0` NAT),
  the `~/.local/share/ansible-managed/vm-incus/` home namespace, the `wait_ready` readiness
  contract (agent answers + IPv4 default route + DNS).
- [ ] Host prerequisites (incus + `incus` group; firewalld `trusted` zone on FW hosts; storage pool).

**`DESIGN.md` (architecture - "how/why"):**
- [ ] Host-side provisioning (NO ansible/python in the guest; `incus exec` from host) - §5/§8.1.
- [ ] Metadata-driven argparse (the tables + `build_parser`/`main` loops) - the "edit these together" map.
- [ ] Key mechanisms: `wait_ready`, shadow masks, cwd->VM resolution, shared prebuilt provision
  assets, storage-pool inspector, `expose` IPv4 pin.
- [ ] Why `incusbr0` not the per-user `incusbr-<uid>`; the firewalld trusted-zone dependency.

**Steps:** [ ] 0 confirm REDESIGN disposition -> [ ] 1 write SPEC -> [ ] 2 write DESIGN (distill
§8) -> [ ] 3 repoint ivm docstring + README; retire/archive REDESIGN per step 0 -> [ ] 4 verify
no dangling links.

## `wait_ready` failure - print copy/paste diagnostics after the error - PLAN (2026-06-24)

**STATUS 2026-06-24: DONE + committed** (code `83b07e7`; firewalld-signature detect `69800cf`).
Steps 1-2 done. Step 3 verify - `py_compile`, `ivm --help` smoke, and a render harness for BOTH
die branches (generic "no connectivity" + the firewalld "IPv6 but no IPv4" signature) all GREEN;
the diagnostics block fills in real name+bridge with the correct sudo/no-sudo split. `make
vm-incus-sandbox` could NOT finish in the CI/Claude env (builds the image + starts the container,
but systemd-as-PID1 never reaches ready in 90s - same documented limitation as the set/unset
section); run it on a real host for the deployment check.

**Why.** When `wait_ready` dies ("no network connectivity after 60s ..."), it gives no next step
(user: "meaningless"). Print the EXACT debug commands - the ones that cracked the 2026-06-24
firewalld incident - right after the error, ready to copy/paste back.

**What.** `wait_ready` (ivm ~L1080-1096) `die()`s with a static string. Append a DIAGNOSTICS block
with values FILLED IN (no `<...>` placeholders - CLAUDE.md): real VM name + the VM's resolved
bridge (read `devices.eth0.network` from `incus config show --expanded <name>`; fall back
`incusbr0`). MUST get sudo right (the bug we just hit): **`incus exec` = NO sudo** (runs in the
user's `user-<uid>` project; `sudo incus` -> root's `default` project -> "Instance not found");
ONLY `incus network show` + `firewall-cmd` take sudo.

Block to print (order that diagnosed it; `NAME`/`BR` substituted live):
```
  incus exec NAME -- ip addr show
  incus exec NAME -- ip route show default
  incus exec NAME -- networkctl status
  incus exec NAME -- journalctl -u systemd-networkd --no-pager -n 50
  sudo incus network show BR
  sudo firewall-cmd --get-zone-of-interface=BR          # 'no zone'/'public' => DHCP dropped
  sudo firewall-cmd --zone=trusted --change-interface=BR                       # runtime fix
  sudo firewall-cmd --permanent --zone=trusted --change-interface=BR && sudo firewall-cmd --reload
  ip link show master BR
```

**Steps:** [x] 1 add `_resolve_vm_bridge(name)` (expanded cfg -> eth0.network; default incusbr0)
-> [x] 2 rewrite the die() to print cause + filled-in block to stderr, ONE message, reuse the
existing TTY/NO_COLOR gating -> [x] 3 verify `py_compile`, eyeball real name+bridge + correct
sudo/no-sudo split (DONE); `make vm-incus-sandbox` blocked by the env (systemd-not-ready) - real host.

## `incusbr0` firewalld zone - survive reboot + ivm self-diagnose - PLAN (2026-06-24)

**STATUS 2026-06-24: steps 1 + 4 DONE + committed; steps 2, 3, 5 BLOCKED on a real host.**
Step 1 (host-install permanent binding self-heals) `0c758ec`; step 4 (ivm DETECT+INSTRUCT in
`wait_ready`) `69800cf`. Steps 2 (reboot-test - "the open question"), 3 (conditional oneshot unit,
only if step 2 fails), and 5 (reboot + all-VMs-get-IPv4 verify) NEED A REAL HOST with incus +
firewalld; this CI/Claude env has neither a reboot nor a working systemd-in-podman sandbox. ->
flagged in the closing question to the user.

**Incident.** Full diagnosis + decisions: see the **"2026-06-24 network incident" log at the top**.
TL;DR: incusbr0 in no firewalld zone -> default `public` DROPs DHCP udp/67 -> IPv6 SLAAC but no
DHCPv4 lease; the `--permanent` binding was EMPTY on this host (L803 fix never persisted). Upstream
incus firewalld howto confirms `trusted` is the fix AND warns the firewall can erase incus rules if
started after the incus daemon - so boot ordering matters (drives step 3).

**Answer to "should ivm self-solve?"** ivm must NOT silently `sudo firewall-cmd` - it talks to
incus as the UNPRIVILEGED user via the socket, never sudo, and CLAUDE.md requires transparency
before privileged actions. Split the responsibility:
- **ivm = DETECT + INSTRUCT** (no privilege): on `wait_ready` failure, if the agent answers AND
  the guest has a global IPv6 but no IPv4 default route, print "host is dropping DHCP - likely
  firewalld zone" + the fix command (the sibling PLAN's diagnostics block). User runs the sudo line.
- **host-install role = make it DURABLE** so it stops happening.

**Durability (host-install) steps:**
- [x] 1. Make the L803 task self-healing: set the `--permanent` trusted binding when EITHER
  runtime OR permanent is missing (today it only checks runtime; this host had neither).
  **DONE `0c758ec`** - now queries BOTH runtime AND permanent (`firewall-cmd --permanent
  --get-zone-of-interface`, the documented permanent query) and re-asserts unless both are `trusted`.
- [ ] 2. REBOOT-TEST on a real host: with the permanent binding set, does firewalld re-apply
  `incusbr0 -> trusted` when incus creates the bridge on boot? (Upstream does NOT promise it for
  interfaces created AFTER firewalld loads.) **This is the open question.**
- [ ] 3. If it does NOT survive: deploy (firewalld hosts only) a oneshot unit
  `incusbr0-firewalld-trust.service`, `After=incus.service firewalld.service`,
  `ExecStart=firewall-cmd --zone=trusted --change-interface=incusbr0`, `WantedBy=multi-user.target`
  - re-asserts the zone last on every boot (also covers the "firewall after incus erases rules" warning).
- [x] 4. ivm self-diagnose: implement DETECT+INSTRUCT in `wait_ready` (shares `_resolve_vm_bridge`
  with the diagnostics PLAN). **DONE `69800cf`** - `_guest_global_ipv6_but_no_ipv4` probes via the
  already-answering agent; on the signature the die() leads with "host is DROPPING the guest's
  DHCPv4 ... firewalld zone" + the fix block. No auto-sudo (DETECT+INSTRUCT only).
- [ ] 5. Verify: re-run `vm-incus-install` (idempotent, sets permanent); reboot host; all VMs get
  IPv4 with NO manual step; `make vm-incus-sandbox` for the role bits.

**Interim (user, now):** `sudo firewall-cmd --permanent --zone=trusted --change-interface=incusbr0
&& sudo firewall-cmd --reload`, then reboot once to feed step 2. Default zone staying `public` is
correct - only the internal NAT bridge goes to trusted; real NICs stay public.
