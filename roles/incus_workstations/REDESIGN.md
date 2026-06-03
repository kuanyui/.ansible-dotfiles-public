# incus_workstations redesign notes

Status: **design discussion, nothing built yet.** This file records the
current-state analysis, the design directions explored, and the refactors that
must land *before* the larger `incus-workspaces` rework can start. It is a
working scratchpad, not a finished spec. Each decision below is tagged
**DECIDED** / **LEANING** / **OPEN**.

Terminology note: the current role is `roles/incus_workstations`. The proposed
successor is referred to as `incus-workspaces` here; the final name is itself
**OPEN** (`workstations` vs `workspaces`).

---

## 1. What triggered this

`make apply-incus-workstations` produces no `~/.local/bin/v-<name>` launcher.

Not a bug: `roles/incus_workstations/defaults/main.yml` ships
`incus_workstations: []` (empty). Launchers are rendered by a loop over that
list (`tasks/install.yml:16-21`), so an empty list renders nothing. The role
*does* run (the playbook bypasses the `setup_incus_workstations` gate), there is
just no data to render.

Contrast: `roles/incus_agents` ships default entries (`claude`, `codex`, ...),
so `v-claude` exists out of the box. That is fine for agents because the only
question there is "can this coding agent run". A general workstation VM has a
much larger definition space (OS, resources, GUI, packages, mounts), so the
role cannot pre-decide entries for the user.

This exposed two deeper problems (sections 2-3) that motivate the redesign.

---

## 2. Current-state analysis: two concerns are welded together

The launcher template `templates/v-launcher.sh.j2` mixes three things:

| Concern | Where | Distro-specific? |
| --- | --- | --- |
| VM lifecycle (launch/start/stop/snapshot/mount/gui/rma) | `v-launcher.sh.j2` | No - pure incus |
| Provisioning (install packages, create user, chsh, push dotfiles) | `_run_apt_install` etc. in same file | Yes |
| Package list | `incus_workstations[*].apt_packages` (data) | - |

The provisioning concern is **hardcoded to Debian/apt**:

- `_run_apt_install` (`v-launcher.sh.j2:75-88`) calls `apt-get` directly and
  always installs a Debian baseline (`openssh-server curl git ... zsh tmux`).
- `defaults/main.yml:34` base image defaults to `images:debian/13`.
- `tasks/install.yml:66-70` stages dotfiles with `override_os_family: Debian`
  and carries a TODO admitting multi-distro is not done.

Consequence (answers "is the set of producible workstations hardcoded?"):

- **Which** workstations get built = data (`incus_workstations` var). Not hardcoded.
- **How** they are provisioned = a single hardcoded Debian/apt path. **This is
  the hardcoded part.** Adding openSUSE today means editing the template; a
  user-set `base_image: images:opensuse/tumbleweed` would reach `_run_apt_install`
  and break (no `apt-get`).

`apt_packages` is the only package field *because the VM is always Debian*.
There is no `zypper_packages` etc.

Note: `v-<name> update` (the `cmd_update` subcommand, `v-launcher.sh.j2:383`) is
**pre-existing**, not part of this proposal. It currently does, inside the VM:
`apt-get update + upgrade`, reinstall packages, re-push dotfiles.

---

## 3. Existing repo infrastructure to reuse (do not reinvent)

The repo is already a multi-distro provisioning system. The launcher's bash
`apt-get` duplicates capabilities that already exist:

| Component | Purpose | Distros |
| --- | --- | --- |
| `roles/_install_distro_packages` | ansible-core multi-distro package install; takes `{Debian/Suse/RedHat: {install:[...], probe?}}`; shells `zypper --non-interactive` on Suse, `apt`/`dnf` elsewhere | Debian / Suse / RedHat |
| `roles/distro_packages` package groups (renamed from `roles/packages`; now delegates installs to `_install_distro_packages`) | named bundles, each a `{common, debian, suse, redhat}` dict (e.g. `distro_packages_net_tools: {common: [nethogs, traceroute, ...]}`) toggled by `distro_packages_install_*` booleans | Debian / Suse / RedHat |
| `roles/zsh` `install-zsh-from-distro-repo.yml` | install zsh + plugins + chsh, os_family-aware | multi |
| `roles/emacs` `install-emacs-from-distro-repo.yml` | install emacs + emacs packages, os_family-aware | multi |
| `roles/dotfiles` | stage zshrc/bashrc/etc.; already included by `incus_workstations/tasks/install.yml` | - |
| JSON Schema precedent | `roles/apparmor/local_vars/personal_dirs.schema.json` + python validator | - |
| Python precedent | `roles/apparmor/scripts/gen_personal_dirs_aa_mixins.py` (type-annotated, per CLAUDE.md) | - |

Key fact: **openSUSE support already exists in the repo's roles**; the
`incus_workstations` launcher just does not use it.

Also: the repo provisions `hosts: localhost, connection: local`
(`playbooks/user.yml`). "Target hosts are usually VMs" (CLAUDE.md) means *the
repo is run from inside a VM to provision that VM*, not pushed remotely.
ansible-core has no incus/lxd connection plugin (and the project is
ansible-core-only), so "provision the VM with ansible" realistically means
"run this repo inside the VM", not "controller pushes to VM".

---

## 4. The proposed model

### 4.1 Backbone: split the two layers - **DECIDED (direction)**

- **Layer 1 - lifecycle.** Distro-agnostic: launch/start/stop/snapshot/mount/
  gui/rma. Pure incus. Windows reuses this unchanged.
- **Layer 2 - provisioning.** Pluggable per distro family. This is the part
  that is hardcoded today.

### 4.2 Packages: presets are named macros over raw per-family lists - **LEANING (strong)**

The tension "curated presets vs let users write raw apt/zypper" is a false
choice. There is one primitive - a per-os_family package list - and a preset is
just a reusable *name* that expands into that primitive. Same mechanism, not two
systems:

```yaml
# in a VM definition:
presets: [qtdev, firefox]        # curated, reusable, cross-distro names abstracted once
packages:                         # raw escape hatch for the long tail / version-pinned names
  debian: [python3.13, python3.13-venv]
  suse:   [python313]
```

Install set for the host's family F = `(presets expanded for F) ∪ (raw packages for F)`.

- Worth abstracting once, shared by many VMs (a desktop env, a base dev
  toolchain) -> make it a preset.
- Dirty, version-pinned, one-off (`python313` vs `python3.13`) -> raw list, does
  not pollute the preset registry.

This resolves the cross-distro name divergence (`firefox-esr` vs
`MozillaFirefox`): the divergence is encoded once, inside the preset definition.

### 4.3 Reuse of `roles/distro_packages` - **DECIDED**

Reuse the *convention* (`{common/debian/suse/redhat}` dict) and the *install
engine* (`_install_distro_packages`). Do **not** make VM presets be
`roles/distro_packages` itself - that role is too coarse (4 host-tool bundles)
and boolean-toggled, wrong shape for composable, app-level, per-VM presets. New
preset registry, standing on the existing install primitive.

(Done in section 6.1: `roles/packages` was renamed to `roles/distro_packages`
and rewired to delegate installs to `_install_distro_packages`, which fixed a
latent ansible-core violation - the old role used `ansible.builtin.package`,
which dispatches to `community.general.zypper` on openSUSE.)

### 4.4 Definition source of truth - **RECOMMENDED (user leaning)**

YAML (JSON-Schema-validated) is the source of truth. A CLI may exist as
convenience, but **CLI flags must never be the only place a VM is defined** -
that loses declarativeness, version control, and reproducibility. If a CLI
spins up an ad-hoc VM, it writes the definition back to YAML.

### 4.5 Per-VM YAML file + inheritance - **LEANING / OPEN**

- One YAML file per VM: better for a real fleet (independent git diffs,
  drop-in/out). For a tiny fleet the current single list is also fine.
- Inheritance: if used, keep it **single-level `extends`** with explicit merge
  semantics (lists append, scalars override, no multiple inheritance / diamond).
  Lighter alternative for a small fleet: one global `defaults` block + presets,
  skipping inheritance entirely.
- Decision hinges on fleet size: ~<=3 VMs -> defaults+presets; ~10+ -> `extends`.
  **OPEN: how many VMs is this fleet expected to hold?**

```yaml
# illustrative only
# vms/base-debian13.yml
os: debian13
cpu: 4
memory: 8GiB
presets: [base-dev]

# vms/qtdev.yml
extends: base-debian13
presets: [qtdev, firefox]   # merged (append) with base
memory: 16GiB               # scalar override
```

### 4.6 Engine: single python CLI vs N bash launchers - **LEANING (python)**

Today each VM is a ~450-line bash script, near-identical except baked-in config.
Adding 3 OS branches + preset composition + a radically different Windows path
would mean maintaining that branching across N bash copies - bad. A single
python `incus-workspaces` engine (one codebase, real data structures, testable,
type-annotated per CLAUDE.md) is more maintainable. The `v-<name>` ergonomics
can be preserved with thin generated shims: `v-qtdev` -> `incus-workspaces --name qtdev`.

CLI sketch the user floated:
`incus-workspaces init --name debian13qtdev --os debian13 --presets qtdev firefox emacs vscode`
- acceptable as a convenience entry point, subject to 4.4 (must persist to YAML).

### 4.7 OS selector - **OPEN (detail)**

Need a small map: friendly token (`debian13`) -> incus base image
(`images:debian/13`) + os_family (`Debian`). os_family is what presets and
`_install_distro_packages` key on.

### 4.8 Windows - **DECIDED (separate tier), phased later**

Windows shares only Layer 1 (lifecycle). It cannot use the unix provisioning
(no apt/zypper, no zsh/emacs dotfiles, no `incus exec zsh` shell). It is its own
provisioner tier:

| | Debian/openSUSE/RedHat | Windows |
| --- | --- | --- |
| install | apt/zypper/dnf | winget/choco or unattend.xml |
| first-boot setup | `incus exec` shell | cloudbase-init / sysprep |
| access | `incus exec` shell | RDP (not a zsh shell) |
| dotfiles | push ~/.zshrc, chsh | n/a |

The "share with the project's dotfiles" benefit does **not** extend to Windows.
Windows-in-incus is a large chunk on its own (UEFI/secureboot, virtio drivers,
RDP/SPICE access, cloudbase-init/unattend.xml) and is orthogonal to the
Debian/openSUSE sharing work. Plan: this rework lands the Layer 1 interface so
Windows *can* use lifecycle; the `.ps1` provisioner comes later.

---

## 5. THE upstream open question - blocks everything else

**OPEN: is a preset packages-only, or can a preset pull an ansible role?**

| Option | Implication |
| --- | --- |
| Packages-only | preset registry is pure data (`{debian:[], suse:[]}`); the engine resolves names and installs; **VM needs no ansible**. Simple. |
| Can pull a role | `emacs`/`vscode` presets run `roles/emacs` etc., reproducing emacs.d/config; **requires running ansible inside the VM**. Powerful, heavier. |

This single decision determines:
- whether the VM must contain ansible-core,
- whether presets live as python data or ansible vars,
- whether "share the project's zshrc/bashrc/emacs.d" is literal (same roles run
  in the VM) or just "same dotfile contents staged + pushed".

Concrete framing for the user: **do the VM's emacs/vscode need to reproduce your
host config (emacs.d etc.), or is installing the package enough?**

---

## 6. Prerequisite refactors (do these to the *current* state first)

The user wants to refactor the current state before building `incus-workspaces`.
Ordered by independence from the open question in section 5.

### Safe now (independent of section 5)

1. **Rename `roles/packages` -> `roles/distro_packages`. [DONE]** Justified by
   CLAUDE.md naming rules ("name must answer X of what" - these are distro
   packages, not pip/npm) and aligns with `_install_distro_packages`. Landed:
   - `git mv roles/packages roles/distro_packages`,
   - `playbooks/root.yml` role-list ref,
   - `group_vars/all.yml` toggles (`packages_install_*` -> `distro_packages_install_*`),
   - in-role var names (`packages_basic_tools` -> `distro_packages_basic_tools` etc.),
   - `scripts/sandbox/configs/root.py` + `scripts/sandbox/sandbox.py` (functional + comments),
   - docs: `README.md`, `Makefile` help, `CLAUDE.md` example.
   Also rewired the install path to delegate to `_install_distro_packages`
   (was `ansible.builtin.package`, which violated ansible-core-only on Suse).
   Note: any personal `local_vars/` overrides using the old `packages_install_*`
   names must be updated, or they will be silently ignored.

2. **Document / freeze the Layer 1 vs Layer 2 split** in the current launcher so
   the boundary is explicit before any engine swap.

### Blocked on section 5

3. **Replace the hardcoded `_run_apt_install`** with either:
   - python resolving presets + `_install_distro_packages`-style installs
     (packages-only), or
   - running the repo's roles inside the VM (role-backed presets).
   Cannot finalize until section 5 is answered.

4. **Adopt the `{Debian/Suse/RedHat}` dict shape** for the per-VM package field
   (replacing flat `apt_packages`), plus a JSON Schema for the VM definition.

5. **Stage emacs.d / bashrc** into the VM the way zsh/dotfiles already are (only
   if section 5 lands on "role-backed").

---

## 7. Decisions snapshot

| # | Topic | Status |
| --- | --- | --- |
| 4.1 | Two-layer split (lifecycle vs provisioning) | DECIDED (direction) |
| 4.2 | presets = named macros over raw per-family lists; offer both | LEANING (strong) |
| 4.3 | Reuse `_install_distro_packages` + dict convention, new preset registry | DECIDED |
| 4.4 | YAML source of truth + schema; CLI only as convenience | RECOMMENDED |
| 4.5 | Per-VM YAML; single-level `extends` vs defaults+presets | OPEN (fleet size) |
| 4.6 | Single python engine + `v-<name>` shims | LEANING (python) |
| 4.7 | OS token -> image + os_family map | OPEN (detail) |
| 4.8 | Windows = separate provisioner tier, phased later | DECIDED |
| 5 | preset = packages-only vs can-pull-a-role | **RESOLVED -> packages-only, no ansible in VM (see §8.1)** |
| 6.1 | Rename `packages` -> `distro_packages` + delegate to `_install_distro_packages` | DONE |
| - | Final name `incus-workstations` vs `incus-workspaces` | OPEN |
| 8 | Merge `incus_agents` + `incus_workstations` into one engine | LEANING (strong) |
| 8.1 | Provision from HOST via `incus exec`; no ansible/python in guest | DECIDED |
| 8.3 | Three-tier install: package_groups / flat packages / post_install_script | DECIDED |
| 8.6 | mounts: declarative `cwd` token (no shell `$(...)`), `/workspaces/` guest, frozen at creation | DECIDED |

---

## 8. Converged design: unified `incus-workspaces` (this session)

Direction shift: **merge `incus_agents` + `incus_workstations` into one engine.**
The two roles are ~90% identical (VM lifecycle + provisioning + the two-variant
dotfiles staging, already shared via `_incus_guest_setup_dotfiles`). The only
real difference is the VM identity model (per-project cwd vs fixed). "claude"
stops being a special "agent" - it is just a VM definition whose
`post_install_script` installs Claude Code. **There is no `agent` abstraction.**

Evidence for merging: this session added the SAME y/N create gate, the SAME
`user.*` tags, and the SAME dotfiles staging to BOTH ~500-line launchers
separately - the duplication tax of keeping them split.

### 8.1 Provisioning runs from the HOST, not inside the VM - **DECIDED (resolves §5)**

§5 resolved to **packages-only + post_install hook, NO ansible in the guest.**
Rationale: embedding ansible-core forces python into every guest, even a minimal
one the user explicitly wants kept tiny. The host-side engine orchestrates via
`incus exec`:

- `incus launch` + attach mounts (validate `host` paths exist at init)
- `incus exec` -> native package manager (apt/zypper/dnf) installs `packages` + expanded `package_groups`
- `incus exec` -> run `post_install_script`
- push the host-staged dotfiles (the user/root variants already built)

Guest gets **zero ansible / zero python** unless the VM itself installs them.
"Share the project's emacs.d etc." happens via dotfiles staging (extend the
existing push), NOT by running roles in the VM.

### 8.2 VM definition schema (one file per VM)

```yaml
name: claude
os:
  type: debian              # specific distro (debian/ubuntu/opensuse/fedora); engine derives pkg mgr + os_family
  image:
    source: incus           # incus remote | iso path | virt-builder (TBD)
    uri: debian/13
hardware:
  cpu: 4
  memory: 8GiB
  disk: 30GiB
sys:
  gui: false
  ssh_server:
    enabled: false
    port: 20023
    root_login: false
    password_login: false
    authorized_keys: ["~/.ssh/id_ed25519.pub"]
mounts:
  - cwd
package_groups:
  - base-dev
packages:
  - curl
  - git
  - ripgrep
post_install_script: |
  curl -fsSL https://claude.ai/install.sh | sh
```

### 8.3 Three-tier "what to install" - **DECIDED**

| Nature of the thing | Field | Why |
| --- | --- | --- |
| Stable, same across distros, reused by many VMs (git/make/ripgrep) | `package_groups` | worth abstracting once |
| VM-specific or version-pinned (`python3.13`) | flat `packages:` (literal name for this VM's distro) | the VM pins ONE distro -> no matrix |
| Precise language runtime, cross-distro (python/jdk/node) | `post_install_script` + version manager (mise/uv/sdkman/nvm/rustup) | distro repos lag/vary; this is the right tool, not a hack |

The cross-distro/version name matrix only appears if pinned things are forced
into a reusable group. A single VM's flat `packages:` never needs a matrix.

### 8.4 `package_groups` registry - **DECIDED (name + location)**

- Name: **`package_groups`** (aligns with the repo's existing `distro_packages`
  "groups" vocabulary).
- Defined centrally in ONE registry file (e.g. `package_groups.yml` beside the
  VM definitions). VM refs by name; engine expands for the VM's distro.
- Keyed by **specific distro** (debian/ubuntu/opensuse/...), NOT just os_family,
  with `common` fallback - because debian vs ubuntu package names diverge.
- Separate registry from host-level `distro_packages_*_tools` (those are
  boolean-toggled host bundles); same `{common, <distro>...}` dict shape.

```yaml
# package_groups.yml
base-dev:
  common: [git, make, ripgrep, tmux]
  debian: [build-essential]
  ubuntu: [build-essential]
  opensuse: [gcc, gcc-c++, make]
```

### 8.5 os / sys schema - **LEANING**

- `os.type` = specific distro; engine derives package manager + os_family.
  `os.image.{source,uri}` = where to fetch the disk image, decoupled from type.
- `sys.gui` (bool for now; x11/wayland is a guest-session detail, deferred).
- `sys.ssh_server {...}` = for external / IDE-remote access; the launcher's own
  shell uses `incus exec`, so ssh is NOT needed for that. `authorized_keys` =
  host pubkeys to install (renamed from `authorized_host_key`).
- `hardware.{cpu,memory,disk}`.

### 8.6 mounts - **DECIDED**

- Declarative only - NO shell `$(...)` in YAML (injection / unclear when+where
  it evaluates / breaks "config is data"). A `cwd` token = mount the current dir
  at creation -> `/workspaces/<basename-of-cwd>`. `~` expansion allowed in `host`.
- guest paths live under `/workspaces/` (devcontainer compatibility).
- Mounts applied ONLY at VM creation; frozen once the VM exists (matches "claude
  defaults to cwd, unless the VM is already created").

### 8.7 Still OPEN

- **Naming / scope**: single `v-claude` (cwd-at-creation, frozen) vs per-project
  `v-claude-<project>` (current agents behavior). Decides whether `name` carries
  a project dimension. **UNANSWERED.**
- `sys.ssh_server` intended use = external / IDE access (confirm).
- Final role name: `incus-workstations` vs `incus-workspaces`.
