# Project Guidelines

- All code content (comments, variable names, strings) must be in English.
- The Claude Code execution environment is NOT the user's main development machine. Only read files within the current project directory (pwd). Do not explore paths outside it (e.g. do not `ls /home/user/` or read files from sibling directories).
- Use hyphens (-) not em-dashes (—).
- Ansible: use ansible-core only. Do not use community.general or other collections.
- Ansible task names: expose the underlying variable names directly (e.g. "Packages to install when packages_install_basic_tools is true"). Ansible is already complex and obscure - task names should make the controlling variables immediately visible so debugging requires no reverse-engineering.
- Target hosts are usually VMs (the playbook is mainly used to provision guest VMs, not bare-metal workstations). Consequence: features that themselves spin up a VM/microVM inside the guest - notably `podman_runtime: libkrun` - are off by default (`setup_podman: false`) because nested KVM in a guest is rarely wanted. Keep such VM-in-VM features opt-in; do not enable them globally without an explicit request.
