# roles/vm_quickemu - `qvm`, the quickemu launcher

Installs `qvm`: a typed-Python wrapper around [quickemu](https://github.com/quickemu-project/quickemu)
for the VM axis `ivm` (roles/vm_incus) does not cover - Windows / macOS guests
and 3D desktop Linux. Positioning: [`roles/vm_incus/docs/survey-of-quickemu.md`](../vm_incus/docs/survey-of-quickemu.md).

| | `ivm` (incus) | `qvm` (quickemu) |
| --- | --- | --- |
| Niche | per-project headless Linux dev VM | desktop / Windows / macOS / 3D |
| Image | incus `images:` remote (preinstalled) | prebuilt qcow2 or `quickget` ISO |
| Exec | `incus exec` (TTY) | QEMU Guest Agent (batch) + SSH |
| Storage | incus pool (btrfs loop) | standalone qcow2 per VM - **no pool** |

## What `qvm` fixes vs raw quickemu

- **No interactive install for tumbleweed / debian / fedora.** `qvm init
  tumbleweed` = official Minimal-VM Cloud qcow2 (sha256-verified, cached) +
  cloud-init NoCloud seed ISO (key-only user, passwordless sudo, installs
  `qemu-guest-agent` on first boot). `qvm init debian|fedora` = `virt-builder`
  (GPG-verified; agent + sshd baked in, per-VM ed25519 key injected on root).
  Anything else: `qvm init windows 11` etc. -> `quickget` passthrough
  (Windows = unattended; most Linux ISOs = interactive ONCE).
- **Host->guest exec without SSH/credentials:** `qvm exec -- <cmd>` /
  `qvm push` / `qvm pull` speak the QEMU Guest Agent protocol over the socket
  quickemu already wires (`--display none|spice`). Batch only - QGA returns
  output after the process exits, no PTY. Interactive: `qvm shell` (SSH on the
  auto-forwarded port, per-VM key, per-VM known_hosts).
- **cwd binding like ivm:** subcommands resolve the VM `init`-ed in the current
  dir (or nearest ancestor); `--name <vm>` overrides.

## Commands

| command | what |
| --- | --- |
| `qvm init <os> [name]` | create (prebuilt: tumbleweed/debian/fedora; else quickget) |
| `qvm start [--gui]` | boot headless (default) or SPICE window |
| `qvm stop` / `kill` | ACPI powerdown (monitor socket) / force-stop |
| `qvm exec -- <cmd>` | run in guest via guest agent (root, batch) |
| `qvm push` / `pull` | one file in / out via guest agent |
| `qvm shell` | interactive SSH |
| `qvm snapshot <action>` | qcow2-internal: apply/create/delete `<tag>`, info (VM stopped) |
| `qvm list` / `info` / `delete` | inventory / details / remove (confirms) |

## Storage model (deliberate)

Each VM = `~/.local/share/qvm/vms/<name>/disk.qcow2` + `<name>.conf`. qcow2 is
sparse and snapshots internally - quickemu has **no storage-pool concept**, and
qvm does NOT reuse incus's btrfs loop file (`/var/lib/incus-storage`): that
mount belongs to the incus pool (erased by `make vm-incus-teardown-host`), and
qcow2-on-btrfs is the double-CoW write-amplification combo both projects warn
about. VM data lives OUTSIDE `ansible-managed/`, so `make vm-quickemu-uninstall-qvm`
can never delete a VM.

## Host packages (`make vm-quickemu-install`)

| package | why | availability (repology 2026-06) |
| --- | --- | --- |
| `quickemu` | the engine (pulls qemu) | Debian 13+ / Fedora 41+ official; **openSUSE: NOT packaged** - play warns with manual steps |
| `guestfs-tools` | `virt-builder` (debian/fedora prebuilt path) | all three families, official |
| `xorriso` | cloud-init seed ISO (tumbleweed path) | all three; skipped if genisoimage/mkisofs present |

GUI (`qvm start --gui`) additionally wants a SPICE viewer (`spicy` or
`remote-viewer`); quickemu errors loudly if neither is installed.

## Files

```
roles/vm_quickemu/
  files/qvm                  the launcher (typed Python, stdlib only)
  files/test_qvm.py          unit tests (pure helpers)
  files/completions/         _qvm (zsh) + qvm.bash
  TODO.md                    role-local plan + template-sharing design notes
~/.local/share/ansible-managed/vm-quickemu/   completions (uninstall = rm -rf)
~/.local/share/qvm/                           VM data (NEVER touched by ansible)
```
