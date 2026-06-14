# qvm FIXME - review findings (vs `ivm`)

Cross-read of `files/qvm` against `roles/vm_incus/files/ivm`, the role tasks,
completions, and `REFS/quickemu` (the upstream contract qvm relies on). Three
load-bearing assumptions were re-checked against `REFS/quickemu` and all HOLD,
so they are NOT bugs: `--display none` does wire the `-agent.sock` (l.1767-1772),
`.ports` is truncated each boot so `parse_ssh_port` never reads a stale port
(l.1424), and `qvm start --gui` (`--display spice`) does auto-launch a viewer
(`start_viewer`, l.2174). Items below are real.

Severity: **H** act / **M** decide (cross-OS or ivm-divergence) / **P** parity
gap / **L** docs + fragility.

## H - bugs to fix

| id | where | problem | fix |
| --- | --- | --- | --- |
| H1 | `qvm` cmd_init l.1061/1080/1093 | A failed PREBUILT `init` (download / virt-builder / seed-ISO error) aborts AFTER `vm_dir.mkdir` but BEFORE the `.conf` is written (conf is written last). Result: an orphan `vms/<name>/` with no conf -> `list_vm_records` (globs `*.conf`) never lists it -> `qvm delete` can't target it -> re-`init` dies at `vm_dir.exists()` "already exists". Dead end, needs manual `rm -rf`. `ivm` has no equivalent (incus tracks the half-made instance; `ivm delete` works). | wrap the disk-build in try/except and `rmtree(vm_dir)` on failure, OR write the conf+meta FIRST (before the disk) so `qvm delete` can always find it. |
| H2 | `qvm` l.324, l.336 | `die()` hint says re-run `make quickemu-install` - that target was renamed in REFACTOR Phase 0b. The real target is `make vm-quickemu-install` (confirmed in `Makefile`). A copy-pasted hint fails. | `s/make quickemu-install/make vm-quickemu-install/` (both lines). |

## M - cross-OS / `ivm`-divergence (decide intent)

| id | where | problem | options |
| --- | --- | --- | --- |
| M1 | init_virt_builder_disk l.1014 + push_feature_dotfiles_qga l.728 | **The guest is not prepared the way the shared dotfiles assume.** The dotfiles/registry assets were built for an `ivm` guest: a `user` at uid 1000 with a zsh login shell, baseline installed. `qvm` reuses the same assets but its `init` does NONE of `ivm`'s `provision_script` setup (no `useradd user`, no `usermod --shell zsh`, no timezone/tmpfs/sshd). Concretely: debian/fedora (virt-builder) guests have NO `user` account at all (key injected on `root` only), yet `provision <dotfiles>` still pushes the `home/user` side to `/home/user` uid 1000 (a nonexistent account) and chowns it. tumbleweed gets a `user` via cloud-init but its shell is `/bin/bash`, and `.zshrc` lands with zsh possibly not even installed. | (a) give `qvm` a real baseline step (create `user` uid 1000 + set shells, parity with ivm) and only then push user-side dotfiles; or (b) make `push_feature_dotfiles_qga` skip the `home/user` side when no `user` exists, and document that qvm guests are root-only unless a baseline is provisioned. Pick one and write it down - today it silently misapplies. |
| M2 | qga_push_tree l.719-725 | Ownership is fixed with `chown -R uid:gid <dest>` over the WHOLE destination (`/home/user`, `/root`), not just the pushed files. `ivm` sets per-file ownership via `incus file push --uid`. A second `provision` (or any pre-existing content under `/home/user`) gets re-owned wholesale. | chown only the pushed top-level entries (track them in the loop), not the entire home/root tree. |
| M3 | cmd_shell l.1272 | `qvm shell` does NOT start a stopped VM (`ivm shell` calls `ensure_up`). On a stopped VM it reads the last `.ports` line and execs `ssh` -> "connection refused", not a clear message. | either start+wait like ivm, or check `vm_pid_if_running` and `die("VM not running - qvm start first")`. |
| M4 | cmd_stop l.1232 | `qvm stop` is fire-and-forget ACPI (`system_powerdown` then returns). A scripted `qvm stop && qvm delete` races: `delete` sees the pid still alive and refuses. `ivm`'s `incus stop` is synchronous. | poll `vm_pid_if_running` for a few seconds after powerdown (or have `delete` wait briefly), so stop->delete is reliable. |

## P - parity gaps vs `ivm` (add if wanted)

| id | gap | note |
| --- | --- | --- |
| P1 | no `qvm update` | `ivm update` = refresh + upgrade all pkgs. Notable because tumbleweed is ROLLING (the role already cares about image staleness) - a long-lived TW guest has no in-tool upgrade. |
| P2 | no `qvm resize` | `ivm resize` changes cpu/ram/disk. For qvm today you hand-edit `<name>.conf` (ram/cpu) + `qemu-img resize` (disk). A helper would match ivm. |
| P3 | `qvm init` does no baseline | `ivm init` always installs a baseline + pushes bash/tmux/zsh. A fresh `qvm init` guest is the bare cloud/virt-builder image (`qvm shell` = `/bin/bash`, no dotfiles). If intentional, say so in the README; the symmetry with ivm's always-on baseline is otherwise surprising. (Ties into M1.) |

## L - docs / fragility / perf

| id | where | problem | fix |
| --- | --- | --- | --- |
| L1 | `qvm` l.196 | Generated `.conf` comment says `Managed by qvm (roles/quickemu_vm)` - the role was renamed to `vm_quickemu` (Phase 0b). Written into EVERY VM's conf. | `s/roles/quickemu_vm/roles/vm_quickemu/`. |
| L2 | `completions/qvm.bash` l.3 | Comment points at `roles/dotfiles/.bashrc.j2`; Phase 0d split it - the file is now `roles/bash/templates/.bashrc.j2`. | update the path. |
| L3 | render_cloud_init_user_data l.948 | cloud-init user-data does not pin `uid: 1000` for `user`, but `push_feature_dotfiles_qga` hardcodes uid 1000. Works only because openSUSE's cloud image happens to give the first user 1000 - fragile. | add an explicit `uid: 1000` to the cloud-config user. |
| L4 | qga_guest_exec_wait l.587 | `guest-exec` uses `capture-output: "separated"`, which needs a guest-agent from QEMU >= 7.1. All current targets satisfy it, but it's an undocumented floor (older guest agents reject it -> exec fails). | note the floor in the QGA section comment. |
| L5 | qga_push_tree l.704-718 | dotfiles push is file-by-file over QGA: per file a `mkdir -p` (guest-exec) + a `guest-file-write`, each its own `guest-sync` round-trip. O(files) - slow for a big tree (e.g. `emacs/.emacs.d`). `ivm` does one `incus file push --recursive`. | consider tar -> single `guest-file-write` -> `tar -x` via guest-exec, or just note the cost. |
| L6 | cmd_start l.1204 | A bare `qvm start` (no `--public-dir`) inherits quickemu's default and shares `~/Public` into the guest over 9p - even headless. Possibly surprising. | document it, or default `--public-dir` to `none` and make sharing opt-in. |
| L7 | cmd_init l.1095 + init_provision_after_boot l.1149 | `qvm init <prebuilt> --provision` with NO units boots the VM, then just lists the registry and returns (no provisioning, no agent wait) - an odd outcome for "provision nothing". | treat a bare `--provision` on init as an error (or list without booting). |

## Already tracked (see `TODO.md`)

Real-host validation, "does the TW Minimal-VM Cloud image ship qemu-guest-agent
preinstalled?", and virt-builder's root-password behavior are open `TODO.md`
items; L3/L4/M1 are the host-validation pass made concrete.
