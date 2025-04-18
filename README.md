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
```
sudo apt install git stow zsh emacs
git clone https://github.com/kuanyui/.dotfiles-public.git
cd .dotfiles-public
# run stow commands
```
