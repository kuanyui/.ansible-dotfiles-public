# .ansible-dotfiles (Public Version)
## What is This?
- A minimalized dotfiles managed via Ansible, for quickly setuping a fresh install of a Linux system, especially for either:
  - Virtual machine
  - Server / VPS
  - `root` account
- Not contains any personal / sensitive information (e.g. username, `hostname`, `~/.ssh`, `~/.gitconfig`...etc) is included.
- Can `git clone` via HTTPS (in other word, without SSH key).
- Safe to use for `root` - all related (zsh, emacs...etc) packages are either installed via distro's official package repo, or manually audited (ex: 3rd-party Emacs packages).
- Primarily tested on Debian 13 and Fedora 44, but should work on other distros.

> [!NOTE]
> For dotfiles inside containers (Podman, Docker), see [container-template](https://github.com/kuanyui/container-template) instead.

## Directory Structure

Managed with Ansible roles, following is Ansible directory structure conventions and what each role does:

```sh
playbooks/                # entry playbooks
  ├─ user.yml             # ├─ deploy dotfiles + emacs + zsh + container_apps + apparmor + trusted_pubkeys for current user
  ├─ root.yml             # ├─ same for root (no container_apps/apparmor/trusted_pubkeys)
  ├─ all.yml              # ├─ user.yml + root.yml
  ├─ podman_oci_runtimes.yml  # ├─ dedicated entry: configure podman OCI runtime(s)
  ├─ container_apps.yml   # ├─ dedicated entry: install c-<template>-<runtime> launchers
  ├─ container_apps_uninstall.yml   # ├─ uninstall flow (reads install manifest)
  ├─ vm_incus.yml         # ├─ dedicated entry: install the `ivm` Incus VM launcher
  ├─ vm_incus_uninstall.yml      # ├─ uninstall flow (removes `ivm` + role subdir)
  ├─ vm_quickemu.yml      # ├─ dedicated entry: install the `qvm` quickemu VM launcher
  ├─ vm_quickemu_uninstall.yml   # ├─ uninstall flow (removes `qvm` + role subdir; VMs untouched)
  ├─ apparmor.yml         # ├─ dedicated entry: deploy AppArmor profiles for desktop GUI apps
  ├─ trusted_pubkeys.yml  # ├─ dedicated entry: pin GitHub/GitLab SSH host keys + Debian CD signing keys
  ├─ firefox_tunes.yml    # ├─ dedicated entry: write per-profile user.js (session-store + cache off the SSD)
  └─ mpv.yml              # └─ dedicated entry: deploy mpv config (`vo=wlshm` + keybindings + Lua scripts)
inventory.ini             # hosts and groups (localhost only)
ansible.cfg               # project-level Ansible config (incl. custom `ansible_managed`)
callback_plugins/         # local ansible callback plugins (profile_tasks for per-task timing)
group_vars/
  └─ all.yml              # global variables + `setup_*` opt-in gates + `shared_*` partials
roles/                    # see Roles table below
scripts/                  # standalone helper scripts (apparmor profile gen / sandbox dry-run)
```

### Roles

Roles prefixed with `_` are internal sub-roles invoked via `include_role`; they have no paired playbook and are not standalone entry points.

| Role | Purpose |
|---|---|
| [`_shared/`](roles/_shared/) | Byte-identical dotfile fragments included by `bash` / `zsh` / etc. Templates only, no tasks. |
| [`_install_distro_packages/`](roles/_install_distro_packages/) | Cross-distro package install (zypper / apt / dnf); ansible-core-only, avoids `community.general.zypper`. |
| [`bash/`](roles/bash/) | Deploy `~/.bashrc` (root gets a trimmed variant via `is_root`). |
| [`tmux/`](roles/tmux/) | Deploy `~/.tmux.conf` (static; identical for user + root). |
| [`zsh/`](roles/zsh/) | Install zsh + plugins, deploy `.zshrc`, run `chsh`. |
| [`emacs/`](roles/emacs/) | Install Emacs + elisp packages. |
| [`provision_distro_packages/`](roles/provision_distro_packages/) | Frequently-used distro package bundles (basic / net / sys / Wayland tools); delegates installs to `_install_distro_packages`. |
| [`local_lang_pkg_managers/`](roles/local_lang_pkg_managers/) | Redirect npm / pip / pipx / cargo / go global installs from `~/.local/` into `~/.local-lang-pkg-managers/<tool>/`, so XDG + ansible-managed dotfiles stay separable from language-level package state. Opt-in via `make apply-local-lang-pkg-managers`. |
| [`podman_oci_runtimes/`](roles/podman_oci_runtimes/) | Configure podman OCI runtime (e.g. `libkrun` on openSUSE for VM-isolated rootless containers). |
| [`container_templates/`](roles/container_templates/) | Render per-`(template, runtime)` Makefile / Dockerfile / dotfile trees consumed by `container_apps`. |
| [`container_apps/`](roles/container_apps/) | Install `c-<template>-<runtime>` launchers into `~/.local/bin/`; one ephemeral podman container per `(template, runtime, project)`. |
| [`vm_incus/`](roles/vm_incus/) | Install `ivm`: define an Incus VM (OS/distro, hardware, mounts, packages, dotfiles) in a YAML template, then `ivm init <template>` / `ivm shell`. One VM per project dir; GUI via SPICE, snapshots, multi-distro (Debian/openSUSE/Fedora). |
| [`vm_quickemu/`](roles/vm_quickemu/) | Install `qvm`: quickemu wrapper for the axis `ivm` doesn't cover (Windows/macOS guests, 3D desktop Linux). Prebuilt tumbleweed/debian/fedora images (zero interactive install), `quickget` passthrough for the rest, guest-agent `exec`/`push`/`pull`, SSH `shell`. |
| [`apparmor/`](roles/apparmor/) | AppArmor profiles for desktop GUI apps (Firefox / Chromium / Edge / VLC / mpv / VSCode / Telegram / Gwenview / Okular / ...). |
| [`trusted_pubkeys/`](roles/trusted_pubkeys/) | Pin well-known public keys for the current user (hardcoded in-repo for audit, not fetched): GitHub/GitLab SSH host keys into `~/.ssh/known_hosts` (no TOFU prompt on `git clone git@...`), plus Debian CD signing GPG keys into a dedicated keyring for verifying Debian images. |
| [`firefox_tunes/`](roles/firefox_tunes/) | Cut Firefox SSD writes for the current user: write a per-profile `user.js` (enumerated from `profiles.ini`) that lengthens the session-store interval and keeps the cache off the SSD (RAM-only, or disk cache on a tmpfs dir). |
| [`mpv/`](roles/mpv/) | Deploy mpv player config to `~/.config/mpv/` (migrated from the legacy stow dotfiles): `mpv.conf` with `vo=wlshm` (pairs with the no-GPU AppArmor profile - no X11, no `/dev/dri`), keybindings, touchscreen Lua scripts. |

## Installation

### Prerequisites

**Debian / Ubuntu**

> [!NOTE]
> On a fresh Debian install, your user may not be in the `sudo` group. If so, run the following first, then re-login:
> ```bash
> su -c "/usr/sbin/usermod -aG sudo $USER"
> ```

```bash
sudo apt install --yes --no-install-recommends git make ansible-core
```

**Fedora / RHEL**
```bash
sudo dnf install --assumeyes git make ansible-core
```

**openSUSE / SLES**
```bash
sudo zypper install --no-confirm git make ansible-core
```

**Arch Linux**
```bash
sudo pacman -S --noconfirm git make ansible
```

### Quick Start

```bash
git clone https://github.com/kuanyui/.ansible-dotfiles.git
cd .ansible-dotfiles
make apply-essentials-all-users
```

This deploys dotfiles for both the current user and root. To deploy separately:

```bash
make apply-essentials-user   # current user only
make apply-essentials-root   # root only (requires sudo)
```

## Using the `c-<template>-<runtime>` launchers without applying `roles/bash` / `roles/tmux` / `roles/zsh`

If you already have your own `.bashrc` / `.zshrc` and only want the container app launchers (`c-claude-crun`, `c-claude-krun`, ...) from `make apply-container-apps`, three things need to be wired up in your shell rc manually. The dotfiles role does these for you automatically; this section is for users who maintain their own shell config.

### 1. `~/.local/bin` in `PATH`

Most modern distros do this for you (systemd's `user-environment.d/`, or `~/.profile` on Debian). Verify with `echo $PATH | tr : '\n' | grep '\.local/bin'`. If missing, add to **`~/.bashrc`** AND **`~/.zshrc`**:

```sh
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
```

### 2. bash tab-completion for the launchers

Add to **`~/.bashrc`**:

```bash
# Ansible-managed bash completions. Each managed role drops its scripts under
# its own `~/.local/share/ansible-managed/<role>/bash-completions/` subdir
# (`container_apps`, `incus`, ...); the outer loop globs across all roles
# so new roles don't require editing this snippet. We do NOT use the XDG
# bash-completion dynamic-loader path because that requires the
# `bash-completion` package on every target distro - eager-source here is
# unconditional and cross-distro.
for _comp_dir in "${HOME}/.local/share/ansible-managed"/*/bash-completions; do
    [ -d "$_comp_dir" ] || continue
    for _comp in "$_comp_dir"/*; do
        [ -r "$_comp" ] && . "$_comp"
    done
done
unset _comp_dir _comp
```

### 3. zsh tab-completion for the launchers

Add to **`~/.zshrc`**, **before** any `compinit` call (the `fpath` change is only honored by the next `compinit`):

```zsh
# Ansible-managed zsh completions. Each managed role drops `_<cmd>` files
# under its own `~/.local/share/ansible-managed/<role>/zsh-completions/`
# subdir (`container-apps/zsh-completions/_c-*`, `vm-incus/zsh-completions/_ivm`,
# ...); the glob auto-discovers across all roles. `(N)` is null-glob so it's
# safe even before any role has installed completions.
fpath=(${HOME}/.local/share/ansible-managed/*/zsh-completions(N) $fpath)

# If your .zshrc doesn't already initialize completions, add these two lines
# AFTER the fpath assignment above. If you already call `compinit` somewhere,
# just put the fpath assignment before it - don't call compinit twice.
autoload -Uz compinit
compinit
```

### Verifying it works

After opening a fresh shell:

```sh
# bash
type _c_claude_crun                            # should say "is a function"
complete -p c-claude-crun                      # should print the registered completion
c-claude-crun <TAB><TAB>                       # should list: help env init build run rma rmi rmc ...

# zsh
which _c-claude-crun                           # should resolve to the completion file
c-claude-crun <TAB>                            # should list subcommands with descriptions
```

## VM-isolated launchers via `roles/vm_incus` (the `ivm` launcher)

For workloads where a podman container's shared-kernel boundary feels too thin (e.g. running AI agents that touch source code while sensitive credentials sit on the same host), `roles/vm_incus` installs `ivm`, a launcher that spins up a full Incus KVM VM from a declarative YAML template. The project dir is virtio-fs shared into `/workspaces/<name>` (Incus uses standalone `virtiofsd` with `pivot_root` + seccomp, a stronger isolation boundary than libkrun's in-process virtio-fs).

You describe the VM once (OS/distro, hardware, mounts, packages, dotfiles, post-install) in a template under `~/.local/share/ansible-managed/vm-incus/ivm/templates/<name>.yaml`, then:

```bash
make vm-incus-install          # install `ivm` + example templates
ivm init claude              # create a VM from the `claude` template, bound to the current dir
ivm shell                    # enter it (zsh); `ivm` from a subdir offers the parent's VM
```

`make vm-incus-install` auto-installs the `incus` package, starts + enables `incus.service` AND `incus-user.socket`, runs `incus admin init --preseed` (creates a `default` storage pool + `incusbr0` bridge if not already done), and adds your user to the `incus` group (the lower-privilege user-socket group, NOT the root-equivalent `incus-admin`; the `incus` CLI auto-detects `/run/incus/unix.socket.user` and routes your operations into a per-user project `user-<UID>` for isolation). Each step is gated on a no-`sudo` probe, so on an already-set-up host it does nothing privileged and won't prompt for the become password. (Host-level prep is in `roles/vm_incus` `tasks/host_setup.yml`; details in [`roles/vm_incus/docs/incus-host-setup.md`](roles/vm_incus/docs/incus-host-setup.md).)

If your user was just added to `incus`, **log out + back in** (or `newgrp incus` in this shell) before running `ivm` - the role hard-aborts on this condition so it can't be missed, with the exact remediation steps printed; Linux only refreshes a session's supplementary group set at login time.

Produces `~/.local/bin/ivm` (plus shell completion) + example templates (`claude`, `codex`, ...). You drive it from a project dir:

```bash
cd ~/projects/foo
ivm init claude      # build a VM from the `claude` template (claude.yaml): shares $PWD into
                     #   /workspaces/foo, installs Claude Code, bound to this dir
ivm shell            # zsh into that VM (Claude Code is on PATH inside)
ivm stop             # shut down the VM (disk state preserved)
ivm delete           # delete the VM + its disk (asks first)
```

VM names are derived from `cwd` exactly like `c-claude-crun` derives container names, so `~/work/foo` and `~/sandbox/foo` get separate VMs (bound via the `user.ivm_init_at_dir` tag). Resource defaults come from the template's `hw:` block. Cold boot is ~10-15 s; subsequent `ivm shell` reuses the running VM.

### Threat model: where `ivm` VMs are stronger than `c-*-crun` / `c-*-krun`

| Boundary | `c-*-crun` | `c-*-krun` | `v-*` |
|---|---|---|---|
| Host kernel CVE protection | ❌ shared | ✅ libkrun guest kernel | ✅ KVM guest kernel |
| virtio-fs server sandbox | n/a | ⚠️ in-process (relies on outer podman ns) | ✅ standalone virtiofsd (pivot_root + seccomp) |
| Credentials in `~/.ssh`, `~/.gitconfig` exposure if agent breaks out | ⚠️ visible via mount ns escape | ⚠️ visible via VM escape + ns escape | ✅ not in VM at all; agent never sees them |
| Workflow for committing changes | host or container | host or container | **host only** - VM has no git creds, you `git diff` + `commit` + `push` from the host shell |

# Acknowledgment & Security Declarations

Initially, 2024/07/25, this project was completely written manually, via GNU Stow.

But I feel GNU Gtow is too difficult to maintain and synchronize these dotfiles between multiple systems, so since 2026/04/30, I started to use Claude Code to migrate the whole project into Ansible.

- Now the most of parts are generated by Claude Code, and I manually review each `git diff` and fix if necessary, and never let AI agent have permission to write the `.git/` nor possess permission to run `git push`.
- The 3rd-party packages (e.g. Emacs's `lisp/**/*.el`) are 100% manually copied and audited.
- I always allows AI to access only the essential permissions, and disallow / review any potential dangerous code / actions as possible as I can. But this project still doesn't provide any warranty. Please use by your own risk. (At least, I am personally also using this project heavily.)
