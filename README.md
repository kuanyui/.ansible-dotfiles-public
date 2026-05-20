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
  ├─ user.yml             # ├─ deploy dotfiles + emacs + zsh + container_apps + apparmor for current user
  ├─ root.yml             # ├─ same for root (no container_apps/apparmor)
  ├─ all.yml              # ├─ user.yml + root.yml
  ├─ podman.yml           # ├─ dedicated entry: configure podman OCI runtime
  ├─ container_apps.yml   # ├─ dedicated entry: install c-<template>-<runtime> launchers
  ├─ container_apps_uninstall.yml   # ├─ uninstall flow (reads install manifest)
  ├─ incus.yml            # ├─ dedicated entry: install v-<agent> Incus VM launchers
  ├─ incus_uninstall.yml  # ├─ uninstall flow (reads install manifest)
  └─ apparmor.yml         # └─ dedicated entry: deploy AppArmor profiles for desktop GUI apps
inventory.ini             # hosts and groups (localhost only)
ansible.cfg               # project-level Ansible config (incl. custom `ansible_managed`)
group_vars/
  └─ all.yml              # global variables + `setup_*` opt-in gates + `shared_*` partials
roles/
  ├─ _shared/             # [VIRTUAL] byte-identical dotfile fragments (templates only, no tasks)
  ├─ dotfiles/            # [ROLE] .bashrc + .tmux.conf etc.
  │   ├─ tasks/           #         playbook logic
  │   ├─ files/           #         static files (copy module)
  │   ├─ templates/       #         jinja2 templates (template module)
  │   └─ defaults/        #         default variables
  ├─ zsh/                 # [ROLE] install zsh + plugins, deploy .zshrc, chsh
  ├─ emacs/               # [ROLE] install emacs + elisp packages
  ├─ packages/            # [ROLE] frequently used packages from distro repos
  ├─ podman/              # [ROLE] configure podman OCI runtime (e.g. libkrun on openSUSE)
  ├─ container_templates/ # [ROLE] render Makefile/Dockerfile/dotfiles trees per container variant
  ├─ container_apps/      # [ROLE] consume container_templates output + install ~/.local/bin/c-<name> launchers
  ├─ incus/               # [ROLE] install ~/.local/bin/v-<name> launchers; one Incus KVM VM per (agent, project)
  └─ apparmor/            # [ROLE] AppArmor profiles for desktop GUI apps (Firefox / Chromium / VLC / mpv / VSCode / Telegram / ...)
scripts/                  # standalone helper scripts (apparmor profile gen / sandbox dry-run)
```

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
make apply-all-users
```

This deploys dotfiles for both the current user and root. To deploy separately:

```bash
make apply-user   # current user only
make apply-root   # root only (requires sudo)
```

## Using the `c-<template>-<runtime>` launchers without applying `roles/dotfiles` / `roles/zsh`

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
# Ansible-managed bash completions (deployed by `.ansible-dotfiles-public/roles/container_apps`).
# We do NOT use the XDG bash-completion dynamic-loader path because that
# requires the `bash-completion` package on every target distro. Eager-source
# is unconditional and cross-distro.
if [ -d "${HOME}/.local/share/ansible-managed/bash-completions" ]; then
    for _comp in "${HOME}/.local/share/ansible-managed/bash-completions"/*; do
        [ -r "$_comp" ] && . "$_comp"
    done
    unset _comp
fi
```

### 3. zsh tab-completion for the launchers

Add to **`~/.zshrc`**, **before** any `compinit` call (the `fpath` change is only honored by the next `compinit`):

```zsh
# Ansible-managed zsh completions (deployed by `.ansible-dotfiles-public/roles/container_apps`).
fpath=(${HOME}/.local/share/ansible-managed/zsh-completions $fpath)

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

## VM-isolated agent launchers via `roles/incus`

For workloads where a podman container's shared-kernel boundary feels too thin (e.g. running AI agents that touch source code while sensitive credentials sit on the same host), `roles/incus` provides parallel `v-<agent>` launchers that spin up a full Incus KVM VM per `(agent, project)`. Each VM is a Debian minimal install with the agent native-installed inside, and the project dir is virtio-fs shared into `/workspaces/<name>` (Incus uses standalone `virtiofsd` with `pivot_root` + seccomp, giving a stronger isolation boundary than libkrun's in-process virtio-fs).

### Install

```bash
make apply-incus
```

The role auto-installs the `incus` package, starts + enables `incus.service`, runs `incus admin init --preseed` (creates a `default` storage pool + `incusbr0` bridge if not already done), and adds your user to the `incus-admin` group. Each step is gated on a no-`sudo` probe, so on an already-set-up host it does nothing privileged and won't prompt for the become password.

If your user was just added to `incus-admin`, **log out + back in** (or `newgrp incus-admin` in this shell) before running `v-<agent>` — group membership only refreshes on new login.

For storage layout (where image cache / VM disks land, how the base image is reused across N VMs, how to relocate stuff off `/`), see [`roles/incus/README.md`](roles/incus/README.md).

Produces `~/.local/bin/v-claude`, `~/.local/bin/v-codex` (plus completions). Subcommands mirror the `c-<tpl>-<runtime>` family:

```bash
cd ~/projects/foo
v-claude init        # launch VM, share $PWD into /workspaces/foo, install claude
v-claude claude      # run claude inside the VM
v-claude shell       # bash into the VM
v-claude stop        # shut down the VM (state preserved)
v-claude rma         # rm all: delete the VM and its disk
```

VM names are derived from `cwd` exactly like `c-claude-crun` derives container names, so `~/work/foo` and `~/sandbox/foo` get separate VMs. Resource defaults (4 CPU / 4 GiB RAM / 10 GiB disk per VM) are in `roles/incus/defaults/main.yml`. Cold boot is ~10-15 s; subsequent `v-claude claude` reuses the running VM.

### Threat model: where `v-*` is stronger than `c-*-crun` / `c-*-krun`

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
