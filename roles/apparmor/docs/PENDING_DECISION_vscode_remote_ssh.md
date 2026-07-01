# VS Code Remote-SSH vs AppArmor `~/.ssh` lockdown - PENDING DECISION

Status: OPEN - needs a decision. Raised 2026-07-01. No code changed yet; this is analysis only.

Chosen direction so far: give ssh its own child profile (section 4). Two sub-decisions remain
open (section 8). Revisit when ready.

## TL;DR

The current profile design **does** stop VS Code Remote-SSH from connecting. Root cause: the
vscode profile denies `~/.ssh/` (to protect private keys), and the `ssh` it spawns inherits that
same profile, so ssh cannot read `~/.ssh/config`, `known_hosts`, or private keys. This is a
**deliberate security tradeoff**, not a bug - Remote-SSH's whole job is to read ssh keys, which is
exactly what the profile forbids. The proposed fix (an ssh child profile) works, but only seals
the private key **if** we lean on ssh-agent and refuse to grant the key files at all (section 6).

## 1. The problem: current design blocks Remote-SSH

Failure chain (all references are to the vscode profile
`templates/vscode/local_pathbased_vscode.aa.j2` and the mixins it includes):

1. The profile includes `<abstractions/local_mixin_deny_keyrings>`.
2. That mixin's rule `audit deny @{HOME}/.ssh/{,**} mrwklx,` denies every access mode to
   everything under `~/.ssh/` (`m`=exec mmap, `r`=read, `w`=write, `k`=flock lock, `l`=hard link,
   `x`=execute).
3. In AppArmor an explicit `deny` **overrides any allow**. So the profile's broad
   `owner @{HOME}/** rwk,` (whole home readable) does **not** re-open `~/.ssh/`.
4. The profile ends with `/usr/bin/{,*} rix,`. The `ix` mode = "inherit execute": a program ssh
   spawns keeps running under the **same vscode profile** (it does not transition to its own).
   So `ssh` is bound by the same `~/.ssh/` deny.
5. Default `apparmor_profile_mode: enforce` (defaults/main.yml) means this is hard-enforced, not
   just logged.

Every step Remote-SSH needs then hits the wall:

| Step | Needs | Result |
|---|---|---|
| Extension lists connectable hosts | read `~/.ssh/config` | denied |
| ssh resolves Host alias / IdentityFile / ProxyJump | read `~/.ssh/config` | denied |
| Key authentication | read `~/.ssh/id_*` private key | denied -> `Permission denied (publickey)` |
| Verify remote host fingerprint | read/write `~/.ssh/known_hosts` | denied |

The extension host (the VS Code subprocess that runs extensions) is also under this profile, so
even the "list hosts" step fails before ssh is spawned.

Note: this is the **local** side (VS Code using Remote-SSH to dial out). The **remote** side runs
vscode-server (a node process under `~/.vscode-server/`), which does not attach to this profile
(wrong path, and it is started by sshd), so the remote host is unaffected by this profile.

## 2. Secondary issue: network egress is undefined (leaks in via nameservice)

The vscode profile includes only `<abstractions/local_mixin_network_local_ipc>` (AF_UNIX local
IPC only - Wayland / D-Bus / audio sockets). It includes **neither**:

- `local_mixin_network_app` (the inet/inet6 egress whitelist used by telegram / anydesk), **nor**
- `local_mixin_network_deny` (the inet block used by local viewers).

But it does include `<abstractions/nameservice>`, and that system abstraction grants
`network inet stream` (for DNS/NIS lookups). The header of
`files/profiles/local_mixin_network_deny.aa` already documents this leak; it was also confirmed
present in `/etc/apparmor.d/abstractions/nameservice` on the machine where this was analyzed.

Consequence: ssh's TCP egress (dialing port 22) currently works only **by accident**, inherited
from nameservice. If nameservice stops leaking inet, or a `network_deny` is added, ssh cannot even
complete the TCP handshake. Either way the section 1 (`~/.ssh` lockdown) failure is the dominant
one; fixing egress alone would not help.

## 3. Is this a bug? No - a deliberate security tradeoff

`deny_keyrings` blocking `~/.ssh/` is an intentional decision: stop a compromised editor or a
malicious extension from stealing ssh private keys. VS Code runs untrusted extensions and
untrusted workspace code, so that threat model is sound. Remote-SSH's entire purpose is to read
ssh keys to reach a remote host. **The two goals are in direct conflict; you cannot have both in
full.**

One contradictory signal already in the profile: it keeps
`owner /run/user/*/ssh-askpass-*.sock rw,` (the askpass socket VS Code makes for ssh credential
prompts). So ssh usage was **partly** anticipated - but the `~/.ssh/` deny was never lifted, so
today the askpass channel is open while no key is readable. Remote-SSH is still unusable.

## 4. Chosen direction: an ssh child profile

Instead of `ssh` inheriting the vscode profile (`ix`), route `/usr/bin/ssh` into its **own**
child profile via `cx` (or a standalone `px`) - AppArmor mode qualifiers:

- `ix` = inherit: run under the caller's profile (today's behavior).
- `cx` = child transition: run under a named sub-profile defined inside the parent, e.g.
  `local_pathbased_vscode//ssh`.
- `px` = profile transition: run under a separate top-level profile.

The vscode **main body** (Electron main / renderer / extension host) keeps denying `~/.ssh/`. Only
the ssh child profile is granted what ssh actually needs. So a private key is reachable only from a
tightly-scoped ssh sub-profile, never from the whole vscode process and all its extensions.

## 5. Critical caveat: ssh is NOT a sealed box

Assumption to reject: "ssh only performs operations, it never exposes the private key." ssh is a
tool whose **caller fully controls its argv**, and ssh has several options that make it run an
arbitrary local command. Verified against the OpenSSH `ssh_config(5)` manual
(https://man.openbsd.org/ssh_config):

| Option | Needs an enabling switch? | Effect |
|---|---|---|
| `ProxyCommand` | no | runs a local command via the user's shell `exec` (its stdio becomes the transport) |
| `Match exec` | no | runs a local command; zero exit = condition true |
| `KnownHostsCommand` | no | runs a local command to obtain host keys |
| `LocalCommand` | yes - `PermitLocalCommand=yes` (default `no`) | runs a local command after connect |

All settable from the command line via `-o`, which the caller (VS Code / an extension) fully
controls. The first three need **no** prior switch.

Attack chain **if the ssh child profile were to grant `~/.ssh/` read** (the naive version):

```
ssh -o ProxyCommand="cp ~/.ssh/id_ed25519 ~/leaked" any-host
```

- The `ProxyCommand`'s `cp` runs under the ssh child profile (if subprocesses inherit via `ix`).
- The child granted `~/.ssh/` read -> `cp` reads the private key.
- It writes to `~/leaked`, which the vscode main profile can read (`owner @{HOME}/** rwk`).
- Private key exfiltrated; the connection never even has to succeed.

So a child profile that simply grants the key files is **not** sealed. The child isolates file
access, not process control; VS Code can still drive ssh as a file-read proxy.

## 6. ssh-agent changes the game - real sealing becomes possible

You use `ssh-add` + ssh-agent. With an agent, ssh does **not** read the key file at all: it asks
the agent to sign over `SSH_AUTH_SOCK` (the agent's AF_UNIX local socket). The private key lives
only inside the agent process, which is **outside** any vscode profile.

So the correct design grants the ssh child profile **no** access to `~/.ssh/id_*` key files, only:

| Grant | Mode | Why |
|---|---|---|
| `~/.ssh/config` | r | read host aliases / settings |
| `~/.ssh/known_hosts` | rw | verify and record host keys |
| `SSH_AUTH_SOCK` (usually under `/run/user/*/`) | rw | talk to the agent for signatures |
| inet / inet6 stream | - | outbound handshake to port 22 |

Now the section 5 `cp ~/.ssh/id_ed25519` attack is **blocked by AppArmor**: the child profile
never granted the key files, so `cp` cannot read them. The private key body never enters the
permission scope of any vscode-related profile. This is stronger than the naive plan - even the ssh
child cannot touch the key file.

Keep the agent socket grant OUT of the vscode main profile; put it only in the ssh child profile.

## 7. Residual risks (not 100% sealed)

Key body not leaking is not zero risk. Granting the agent socket grants the ability to **act as**
the key:

1. **Agent socket = borrowed signing capability.** Anything running inside the ssh child profile
   that can reach the socket (including a command VS Code injects via `-o ProxyCommand=...`) can
   ask the agent to sign, i.e. authenticate to arbitrary hosts using your key (lateral movement).
   This is not plaintext key theft, but it is "borrow the key while the agent is unlocked."
   - Mitigation: `ssh-add -c` (confirm - every signature pops a prompt), `ssh-add -t <seconds>`
     (key auto-removed from the agent after a timeout).
2. **The child's network egress can be borrowed** by `-o ProxyCommand="<any outbound command>"`.
   - Mitigation: in the ssh child profile, do not let ssh's subprocesses inherit via `ix`; send
     them via `px` to an even narrower profile (no agent socket, no network). Cost: may break
     legitimate `ProxyJump` (connecting through a bastion/jump host, which spawns a helper).

Both are "ability to exercise the key" risks, a lower tier than "plaintext key exfiltration" -
which section 6 (agent + no key-file grant) eliminates.

## 8. Open decisions to make

1. **Agent-only, or keep a key-file fallback?** Keeping a fallback (grant `~/.ssh/id_*` in the
   child for when no agent is running) is convenient but reopens the section 5 non-sealing. Since
   you always use an agent, the recommended choice is **agent-only, no private-key file grant**.
2. **ssh subprocess handling (`ProxyJump` / `ProxyCommand`):** `ix` inherit (convenient, but the
   child's network/agent can be borrowed) vs `px` narrow (safer, but may block `ProxyJump`). Needs
   to know whether jump hosts are actually used.

## 9. Verification limits

`make sandbox-apparmor` can only confirm: profile syntax is valid, `apparmor_parser` loads it, and
the child-profile transition does not error. It **cannot** reproduce a real VS Code Remote-SSH GUI
connection (needs a GUI + a remote host). So after implementing, the functional path still needs a
one-off on-host test with a real Remote-SSH connection.

## References / file pointers

- vscode profile: `roles/apparmor/templates/vscode/local_pathbased_vscode.aa.j2`
  - the `~/.ssh` lockdown source: `#include <abstractions/local_mixin_deny_keyrings>`
  - ssh inherits the profile: `/usr/bin/{,*} rix,`
  - askpass socket already present: `owner /run/user/*/ssh-askpass-*.sock rw,`
  - only local IPC, no inet mixin: `#include <abstractions/local_mixin_network_local_ipc>`
- `~/.ssh` deny rule: `roles/apparmor/files/profiles/local_mixin_deny_keyrings.aa`
  (`audit deny @{HOME}/.ssh/{,**} mrwklx,`)
- nameservice inet leak documented in:
  `roles/apparmor/files/profiles/local_mixin_network_deny.aa` (header)
- enforce default: `roles/apparmor/defaults/main.yml` (`apparmor_profile_mode: enforce`)
- OpenSSH command-execution options: `ssh_config(5)`, https://man.openbsd.org/ssh_config
