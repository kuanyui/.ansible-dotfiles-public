# dotfiles (Public Version)
## What is this?

- A minimalized dotfile which contains no personal sensitive information.
- Can be `git clone` without SSH key.
- Trustable, can be safely installed for `root`.
- Mainly tested on Debian 12 (bookworm), but should be also used by other distro.

## Suitable Environment
- `root` (`stow -t /root ...`) on localhost desktop.
- Debian in VirtualBox
- Debian on remote server.

> [!NOTE]
> For `.dotfiles` inside containers (Podman, Docker), please see [container-template](https://github.com/kuanyui/container-template) instead.

## How to install

Please `cd` to one of the following folder, then use GNU `stow -t TARGET PACKAGE_NAME` to install.

- `/root/*` is for root.
- `/user/*` is for non-privileged user.

# Quick Start For VM
## Debian-Based
```bash
sudo apt install git stow zsh curl emacs

# user
git clone https://github.com/kuanyui/.dotfiles-public.git
cd .dotfiles-public/user
rm ~/.bashrc
stow -t ~/ zsh emacs bash zsh
chsh -s /bin/zsh

# root (for security concering, separately clone the repo)
su -
git clone https://github.com/kuanyui/.dotfiles-public.git
cd ~/.dotfiles-public/root
rm ~/.bashrc
stow -t ~/ emacs bash zsh
chsh -s /bin/zsh
```
