# quickemu_vm TODO + design notes

Role-local tracker (root `TODO.md` mirrors the cross-repo view; this file holds
the qvm-specific plan + open design discussions).

Status: `[ ]` pending · `[~]` in progress · `[x]` done

## v1 build-out

- [x] **`qvm` launcher** (`files/qvm`, typed Python, stdlib only) - `init` with
  prebuilt images (tumbleweed = official Minimal-VM Cloud qcow2 + sha256 +
  cloud-init NoCloud seed ISO; debian/fedora = `virt-builder` with
  `--install qemu-guest-agent,openssh-server` + per-VM ed25519 `--ssh-inject`),
  `quickget` passthrough for every other OS; lifecycle
  start/stop/kill/delete/list/info; `exec`/`push`/`pull` via the QEMU Guest
  Agent socket (batch only - QGA has no PTY); `shell` via quickemu's
  auto-forwarded SSH port; `snapshot` passthrough (refused live except `info`);
  cwd binding via per-VM `qvm-meta.json`. 15 unit tests (`files/test_qvm.py`).
- [x] **zsh + bash completions** (`files/completions/`).
- [x] **Role + playbooks + Makefile targets + README** - host install
  (quickemu official-repo on Debian/Fedora; openSUSE NOT packaged -> loud warn
  + manual instructions, role continues; `guestfs-tools` + `xorriso`
  everywhere), `qvm_install`/`qvm_uninstall`, `playbooks/quickemu_vm*.yml`,
  `make quickemu-install/check/uninstall-qvm`.
- [ ] **Real-host validation** - this env has no KVM/quickemu. On a real host:
  `qvm init tumbleweed` -> first boot -> cloud-init installs the agent ->
  `qvm exec -- zypper --version`; same for debian/fedora via virt-builder;
  `qvm init windows 11` unattended path; snapshot create/apply offline.
- [ ] **VERIFY: does the TW Minimal-VM `-Cloud` image ship `qemu-guest-agent`
  preinstalled?** The seed installs it via cloud-init `packages:` (needs
  first-boot network) - if it is already in the image, drop the package step
  for a faster first `exec`. Unverified assumption either way; harmless today.
- [ ] **(maybe) `qvm provision`** - thin layer over `qvm exec` consuming the
  SAME `distro-package-groups.json` ivm materializes (see discussion below);
  would give base-tools install on qvm guests without duplicating any package
  list.
- [ ] **No BASELINE dotfiles at `init`** - ivm pushes
  `BASELINE_DOTFILE_FEATURES` (bash/tmux/zsh + `centralize-lang-pkgs-dir`) into
  every guest at `init` and again on `overwrite-dotfiles`; qvm pushes dotfiles
  ONLY on demand via `qvm provision <feature>`, so a fresh qvm guest has no
  managed rc files at all. `cmd_provision` now force-pushes
  `centralize-lang-pkgs-dir` ahead of thirdparty recipes (they source its env
  file, and a missing file aborts the whole `bash -ec` script) - but that is a
  correctness guard for recipes, NOT a baseline. Decide whether qvm should adopt
  ivm's baseline-at-init model or stay fully on-demand by design.

## Design discussion: sharing templates between `ivm` and `qvm`

Raised by the user mid-build ("do you plan to copy `incus_vm`'s templates? not
convenient to share either... unless renaming roles, e.g. `vm_incus` /
`vm_quickemu` / `_vm_shared_template`").

**Decision for v1: qvm copies NOTHING from `roles/incus_vm/files/templates/`.**

Why copying would lie:

| ivm template field | meaning under incus | under quickemu |
| --- | --- | --- |
| `mounts[]` + `shadow` masking | virtio-fs devices via incus API | no conf equivalent (would need hand-rolled qemu args) |
| `distro_package_groups` + provisioning | `incus exec` pipeline | only possible via QGA exec (batch, post-boot) |
| `os.distro` -> image | incus `images:` remote (preinstalled) | prebuilt qcow2 / quickget ISO - different acquisition |
| `hw.tpm` / `hw.secureboot` | incus device/config flags | quickemu decides per guest_os automatically |
| 3D / desktop | impossible (no virgl) | quickemu's whole point |

The two launchers' capability sets genuinely differ - one template schema
pretending to drive both would mostly be fields each side must reject.

**Where sharing IS real: the package-group registry, not the template files.**
`roles/distro_packages/defaults/main.yml` is already the single source of
truth, and `roles/incus_vm` already materializes it to
`incus-vm/ivm/distro-package-groups.json` at apply time. A future
`qvm provision` consumes the SAME registry (rendered to quickemu-vm's subdir by
this role) - zero duplication, no shared-template role needed.

**Role renaming (`vm_incus` / `vm_quickemu` / `_vm_shared_template`): deferred,
lean NO.** Big churn (Makefile targets, playbooks, ansible-managed subdir
names, docs) for a sharing layer whose only real shared artifact is one JSON
registry that needs no role of its own. Revisit only if a third VM backend ever
appears.

**`ivm` side wish (user): `base_{debian,opensusetw,fedora}` templates** - bare
guests with just the baseline/basic tools, no app payload. That belongs to
`roles/incus_vm` (new `templates/base_*.yaml`, trivially expressible in the
existing schema: `os.distro` + `distro_package_groups: [tools_basic]`, no
mounts/gui). Note the symmetry once both exist:

    ivm init base_opensusetw   <->   qvm init tumbleweed
    ivm init base_debian       <->   qvm init debian
    ivm init base_fedora       <->   qvm init fedora

- [ ] **(ivm, separate pass) add `templates/base_{debian,opensusetw,fedora}.yaml`**
  - baseline + `tools_basic` only; decide whether `ivm init` default-suggests
  them. Tracked here so the discussion has a home; implement in `roles/incus_vm`.
