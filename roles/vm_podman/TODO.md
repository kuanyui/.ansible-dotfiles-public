# roles/vm_podman TODO

Durable, role-local notes (same convention as the repo-root TODO.md and
`roles/vm_incus/TODO.md`). Status: `[ ]` pending · `[~]` in progress · `[x]` done

## Goal: align `pvm` subcommands with `ivm` (the newest launcher) - PLAN (2026-06-24)

`ivm` (roles/vm_incus) is the reference launcher. Bring `pvm`'s subcommand surface
as close to `ivm`'s as podman/containers allow. Where containers genuinely cannot
do what an incus VM does, SKIP and write down WHY (so it is not re-derived).

Match `ivm`'s **names** where the concept ports (so muscle memory carries over):
`info`, `push`, `update`, `reboot`, `resize`, `top`, `provision`, `delete`,
`shell`/`sh`/`shell-user`/`shell-root`.

---

## How `pvm`'s CLI is wired TODAY (read this first - every new subcommand edits ALL of these)

`roles/vm_podman/files/pvm` is ONE ~990-line Python script, `argparse`-based. Unlike
`ivm` it is NOT fully metadata-driven (no `CWD_RESOLVED` tables) - it uses two literal
tuple-loops in `build_parser()` + a parallel `if/elif` chain in `main()`. A NEW
subcommand touches **5 places** (miss one = broken/orphaned):

1. **`build_parser()` (~L863-918)** - register the subcommand:
   - template-acting (needs a `<template>` arg): add to the tuple at ~L886.
   - container-acting (acts on the cwd/`--name` container): add to the tuple at ~L902.
   - special args (two-level like ivm `mount`/`set`, or own flags): register by hand
     with its own `add_parser(...)` + `add_argument(...)` (see init's `--rebuild`/`--yes`).
2. **`main()` (~L921-977)** - dispatch:
   - non-container (init/build/run/env/list/help): early-return block (~L930-951).
   - container-acting: add an `elif subcommand == "<x>":` AFTER
     `container_name = resolve_container_for_cwd(...)` (~L954).
3. **the `cmd_<x>()` handler** - the function itself (type-annotated, `--dry-run` aware,
   prints privileged/podman commands before running per CLAUDE.md transparency rule).
4. **zsh completion `files/completions/_pvm`** - add `'name:description'` to
   `_pvm_subcommands` (~L8); add a `case "$words[1]"` arm under `args)` (~L57) IF it
   takes args. zsh is the ONLY shell that shows inline descriptions - use `_describe`.
5. **bash completion `files/completions/pvm.bash`** - add the name to the `subcommands`
   string (~L26); add a `case "$sub"` arm (~L53) IF it takes args. bash lists names only,
   so a no-arg `provision`/`init` must LIST everything (CLAUDE.md).

**Completion data CAN be dynamic, DISPLAY wiring is MANUAL** (CLAUDE.md). Today both
completions read template names dynamically (`_pvm_template_names`) + container names
(`_pvm_container_names`), but the **subcommand list is HARDCODED in both files** - so
every new subcommand must be added to both by hand.

**`pvm` has NO `_pvm_unit_names` yet** (ivm's `provision` unit completion). When `provision`
lands, PORT `_ivm_unit_names` from `roles/vm_incus/files/completions/{_ivm,ivm.bash}` into
BOTH pvm completions (it shells `python3` to read the shared JSON keys + `dotfiles/` dirs).

---

## ivm -> pvm subcommand map (the decisions)

PORT = add it, podman supports the concept · ADAPT = add it, podman semantics differ ·
SKIP = containers genuinely can't, documented · KEEP = pvm already has it.

| ivm subcommand | pvm today | decision | how / why |
|---|---|---|---|
| `init [<tpl>] [<name>]` | `init <tpl>` | KEEP | aligned (pvm derives name from cwd) |
| `list` | `list` | KEEP | aligned |
| `env <tpl>` | `env [tpl]` | KEEP | aligned |
| `shell` / `sh` | `shell` (zsh user) | ADAPT (rename) | add `sh` alias; `shell` = zsh user |
| `shell-user` / `sh-user` | `zsh-user` | ADAPT (rename) | add ivm names as aliases of zsh-user |
| `shell-root` / `sh-root` | `zsh-root` | ADAPT (rename) | add ivm names as aliases of zsh-root |
| `start` | `start` | KEEP | aligned |
| `stop` | `stop` | KEEP | aligned |
| `info` | - | **PORT (P1, high)** | `podman inspect`-based; EVERY field w/ placeholder (CLAUDE.md) |
| `push <local> <guest>` | - | **PORT (P1)** | `podman cp`; `--as-root` => cp then `exec chown` |
| `update` | - | **PORT (P1)** | exec apt/zypper/dnf update+upgrade (per family) |
| `reboot` | - | **PORT (P1)** | `podman restart`; confirm + `--yes` |
| `top [args]` | - | **PORT (P1)** | passthrough to `podman stats` |
| `resize --cpu --memory` | - | **ADAPT (P1)** | `podman update --cpus --memory` (VERIFIED). NO `--disk` (rootless overlay rootfs not resizable) |
| `delete` | `rmc`/`rmi`/`rma` | ADAPT (P1) | add `delete` alias = `rmc` (remove cwd container; KEEP shared per-template image). confirm + `--yes` |
| `provision [<unit>...]` | - | **PORT (P2, big)** | exec install scripts for units into the running container, then `podman commit`. bare = LIST units (bash too). Needs `_pvm_unit_names` in BOTH completions |
| `overwrite-dotfiles` | - | PORT (P2) | re-`podman cp` the dotfiles slice (no reprovision) |
| `mount ls` | hide_dirs@create | ADAPT (P2) | read-only: list the cwd `--volume` + hidden-dir masks from inspect |
| `storage-status [--json]` | - | ADAPT (P3, low) | `podman system df` |
| `set`/`unset shell-dir` | WORKDIR@create | ADAPT (P3, low) | store a label; `cd` there on `shell` |
| `adopt --name` | - | ADAPT (P3, low) | add pvm labels to an unmanaged container |
| `mount attach/detach/shadow` | - | **SKIP** | podman CANNOT hot-add/remove a volume on a running container (VERIFIED: volumes fixed at create). Would need a container recreate - different semantics. Document |
| `expose [<port>]` / `unexpose` | publish_ports@template | **SKIP** | podman CANNOT hot-add a published port on a running container (VERIFIED). Ports are template `publish_ports` set at create. Document |
| `gui` | - | **SKIP** | no SPICE/VM console for a shared-kernel container. (X11-socket forwarding is a different feature) |
| `snapshot <action>` | - | **SKIP** | ivm-style VM disk snapshots N/A. The per-template content-hash image IS a snapshot; `podman commit`/`checkpoint` exist if ever wanted |
| `set`/`unset password <user>` | - | **SKIP** | no console/getty login; entry is `podman exec`. `passwd` inside is pointless |
| `set`/`unset ssh-server <user>` | - | **SKIP** | pvm containers run no sshd; entry is `podman exec`. (NOTE: the DEFERRED libkrun path DOES need sshd - see IMPLEMENTATION_PLAN.md 3.5) |
| `set`/`unset user-sudo` | baked@build | **SKIP** | the container `user` + sudo are baked at build time; no post-hoc toggle |

**pvm-specific extras (NOT in ivm) to KEEP** (podman concepts, no ivm equivalent):
`build`, `run`, `agent`, `rmc`, `rmi`, `rma`, `bash-user`, `bash-root`.

**STATUS 2026-06-24: DONE (P0 + P1 + P2), committed.** Every subcommand implemented and
exercised END-TO-END against real podman 5.4.2 in this env; `test_pvm.py` 20/20; an automated
cross-check confirms the argparse parser, `_pvm` (zsh) and `pvm.bash` agree on all 32
subcommands (ZERO completion drift). P3 deferred (storage-status / shell-dir / adopt).
Commits: emacs-nox `a4d40d1`; shell+lifecycle `a6a6dd4`; info `2f2daf9`; push `ca430b5`;
update `1ea9449`; top `058328f`; resize `cedd675`; provision `2e05959`; overwrite-dotfiles +
mount-ls `b147dbd`; README `8cf4960`.
- **emacs finding (verified rpmfind 2026-06):** `emacs-nox` exists on Debian / openSUSE / RHEL /
  Alma / Rocky / CentOS-Stream, but **current Fedora RENAMED it `emacs-nw`** - so the bundle's
  RedHat overlay is best-effort for Fedora (noted inline in the bundle header).
- **`make vm-podman-sandbox` is ENV-BLOCKED here** (same as ivm): rootless podman cannot run
  systemd-as-PID1 in the Claude/CI env ("not ready within 90s") - the image builds, the
  container will not boot. Re-run on a real host for the deploy/uninstall round-trip diff.
  `ansible-playbook --syntax-check playbooks/vm_podman.yml` passes; the launcher + completions
  are fully covered by the direct real-podman checks above.

---

## P0 - the `emacs` -> X11 bloat fix (the `pvm init claude` bug)

**Symptom.** `pvm init claude` pulls ~13 X11/GTK libs (libgtk-3-0t64, libx11-6,
libcairo2, libxrender1, libxext6, libxrandr2, libxinerama1, libxi6, libxfixes3,
libxcomposite1, libice6, libsm6, libgdk-pixbuf).

**Root cause (VERIFIED, packages.debian.org/trixie 2026-06).** `claude.yaml` pulls the
`emacs` bundle (`roles/provision_distro_packages/defaults/main.yml` L83-86 =
`__common__: [emacs]`). Debian's `emacs` is a METAPACKAGE depending on
`emacs-gtk | emacs-pgtk | emacs-lucid | emacs-nox`; apt picks the first = `emacs-gtk`
(the GUI build), which HARD-Depends the X11/GTK stack. These are Depends not Recommends,
so pvm's `--no-install-recommends` (pvm L359) does NOT strip them.

**Fix (DONE, commit `a4d40d1`).** Use the no-X11 build `emacs-nox` (terminal-only; same editor,
no X11/GTK deps).
- [x] verified the package name per family (rpmfind 2026-06): `emacs-nox` on Debian / openSUSE /
  RHEL / Alma / Rocky / CentOS-Stream; **current Fedora renamed it `emacs-nw`** - bundle uses a
  per-family overlay (Debian/Suse/RedHat = `emacs-nox`), Fedora `emacs-nw` noted inline.
- [x] DECISION (2026-06-24, user): **GLOBAL `emacs-nox`** - the shared bundle, ivm guests
  too (they use emacs as a terminal editor as well, so the X11/GTK build is waste everywhere).
- [x] applied; verified the bundle resolves to `emacs-nox` (no `emacs` metapackage) for every
  family. Full `apt-get install` re-check happens when the sandbox/apply re-renders the cache.

Note: the bundle KEY stays `emacs`, so NO render-dict edit in
`_shared_prebuilt_provision_assets` (CLAUDE.md registry->render-dict rule only triggers on
adding/removing a KEY). If we instead make a NEW `emacs_nox` bundle (pvm-only option), THEN
the render dict + both pvm templates must change.

---

## Work items

Each: implement -> `python3 -m py_compile pvm` + extend `test_pvm.py` -> update BOTH
completions -> `bash -n pvm.bash` + `zsh -n _pvm` -> `make vm-podman-sandbox` (ENV-BLOCKED in
this env, see STATUS; each subcommand was instead verified end-to-end against real podman 5.4.2).

### P1 - high value, podman clearly supports [ALL DONE]
- [x] `info` - `podman inspect`-based. Fields (EACH printed every run, placeholder when
  empty per CLAUDE.md): container name, status, image (per-template ref:tag), template
  (label `pvm.template`), project dir (label, the bound cwd), runtime, hw (cpu/memory
  limits; `(host default)` when none), network mode, published ports (`(none)`),
  mounts (cwd volume + hidden-dir masks `(mask)`; `(none)`), agent (command + display_name;
  `(none)`). Inspect field names verified against podman 5.4.2. Completions: `info` in both.
- [x] `push <local> <guest> [--as-root]` - `podman cp`; `--as-root` => cp then `podman exec
  --user root chown -R`. Completions: both; `_files` for the local path, `--as-root` flag.
- [x] `update` - exec a self-contained per-family upgrade as root (detects apt-get/zypper/dnf).
  Completions: both (no args).
- [x] `reboot` - `podman restart <ctr>`; confirm prompt + `--yes`. Completions: both
  (`--yes`).
- [x] `top [-- podman flags]` - passthrough to `podman stats` (live, exec-replace). `nargs='*'`
  (names) + `--` for flags - REMAINDER mis-parses under subparsers. Completions: both (names).
- [x] `resize --cpu <n> --memory <NG>` - `podman update --cpus <n> --memory <NG>`. Exposes
  ivm's flag names (`--cpu`, `--memory`), maps to podman's `--cpus`. NO `--disk`. Completions:
  both (`--cpu --memory`).
- [x] `delete` - alias of `rmc` (remove the cwd container, KEEP the shared per-template
  image); confirm + `--yes`. Completions: both (`--yes`).
- [x] shell-name alignment - added `sh`, `shell-user`/`sh-user`, `shell-root`/`sh-root` as the
  ivm-aligned set (`shell`/`shell-user` = zsh user, `shell-root` = zsh root) via a
  `SHELL_SUBCOMMANDS` table. Kept `bash-user`/`bash-root`/`zsh-*` as pvm extras. Completions: both.

### P2 - medium / larger [ALL DONE]
- [x] `provision [<unit>...]` - bare = LIST all units (distro groups + thirdparty + dotfiles,
  with descriptions; bash lists too). With units = classify (a unit can be in >1 registry ->
  apply ALL) + exec install scripts into the running container as root; dotfiles via `podman cp`
  (persists in the writable layer, NOT committed - the layer is the container's "disk"). 
  **Completions: PORTED `_ivm_unit_names` -> `_pvm_unit_names` into BOTH `_pvm` and `pvm.bash`**
  (reads the shared JSON keys + `dotfiles/` dirs via `python3`).
- [x] `overwrite-dotfiles` - re-`podman cp` the template's dotfiles slice into the container
  (no reprovision). Completions: both (no args).
- [x] `mount ls` - read-only: list the cwd `--volume` + hidden-dir masks from `podman inspect`
  (reuses info's mount renderer). No `attach`/`detach`/`shadow` (SKIP, see map). Completions:
  both (two-level `mount` -> `ls`).

### P3 - low / optional (confirm before building)
- [ ] `storage-status [--json]` - `podman system df`.
- [ ] `set`/`unset shell-dir <path>` - label + `cd` on `shell` (mirrors ivm shell-dir).
- [ ] `adopt --name <ctr>` - add pvm labels to an unmanaged container.

### Documented SKIPs (no work - keep the reasons in the map above)
`mount attach/detach/shadow`, `expose`/`unexpose`, `gui`, `snapshot`,
`set`/`unset password`, `set`/`unset ssh-server`, `set`/`unset user-sudo`.

---

## DO-NOT-FORGET (historically missed)

- **BOTH completions, every subcommand**: zsh `_pvm` AND bash `pvm.bash`. Each has its own
  hardcoded subcommand list + per-subcommand arg case. The user has flagged dropped
  completions repeatedly - this is the #1 miss.
- **`provision` completion** needs the dynamic `_pvm_unit_names` reader ported from ivm into
  BOTH files (not just the subcommand name).
- **`info` prints EVERY field with a placeholder** when empty (`(none)`/`(unset - ...)`),
  never hides a row (CLAUDE.md launcher-info rule).
- **bare `provision` / `init` LIST everything** (bash too, not just zsh).
- **zsh uses `_describe`** (`name:description`), not bare `compadd`/name lists.
- Update `README.md` subcommand list + `IMPLEMENTATION_PLAN.md` if the surface changes.
- Run `make vm-podman-sandbox` before calling any item done (CLAUDE.md sandbox rule).

---

## Decisions (settled with user 2026-06-24)

1. **emacs X11 fix scope** = **GLOBAL `emacs-nox`** (shared bundle, ivm too). The pvm-only
   alternative (new `emacs_nox` bundle + render-dict + template edits) was declined.
2. **`expose` / `mount attach`** = **SKIP** (document "recreate the container to change
   ports/mounts"); NO adapt-via-recreate in v1 (recreate semantics surprise; the cwd is the
   only durable state anyway).
3. **shell naming** = **KEEP** pvm's `bash-user`/`bash-root` extras alongside the new
   ivm-aligned `shell`/`sh`/`shell-user`/`shell-root`.
4. **Scope** = implement **P1 + P2 now**; P3 deferred (storage-status / shell-dir / adopt).
