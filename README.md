# dotfiles (Public Version)

- No personal/sensitive information - safe to `git clone` without SSH key.
- Safe to use for `root`.
- Primarily tested on Debian 12 (bookworm), but should work on other distros.

> [!NOTE]
> For dotfiles inside containers (Podman, Docker), see [container-template](https://github.com/kuanyui/container-template) instead.

## Directory Structure

Managed with Ansible roles, following Ansible conventions:

```
group_vars/
  all.yml         # global variables (e.g. setup_emacs, setup_zsh)
roles/
  dotfiles/
    tasks/        # playbook logic
    files/        # static files, implicit lookup path for the copy module
    templates/    # Jinja2 templates, implicit lookup path for the template module
    defaults/     # default variables
  emacs/
    tasks/
    defaults/
  zsh/
    tasks/
playbooks/        # entry playbooks
inventory.ini     # defines hosts and groups (here: just localhost)
ansible.cfg       # project-level Ansible configuration (e.g. inventory path, defaults)
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
sudo apt install --yes git make ansible-core
```

**Fedora**
```bash
sudo dnf install --assumeyes git make ansible-core
```

**openSUSE**
```bash
sudo zypper install --no-confirm git make ansible-core
```

**Arch Linux**
```bash
sudo pacman -S --noconfirm git make ansible
```

### Quick Start

```bash
git clone https://github.com/kuanyui/.dotfiles-public.git
cd .dotfiles-public
make apply-all
```

This deploys dotfiles for both the current user and root. To deploy separately:

```bash
make apply-user   # current user only
make apply-root   # root only (requires sudo)
```
