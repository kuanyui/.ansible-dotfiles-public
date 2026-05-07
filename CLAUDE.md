# Project Guidelines

- All code content (comments, variable names, strings) must be in English.
- Use hyphens (-) not em-dashes (—).
- Ansible: use ansible-core only. Do not use community.general or other collections.
- Ansible task names: expose the underlying variable names directly (e.g. "Packages to install when packages_install_basic_tools is true"). Ansible is already complex and obscure - task names should make the controlling variables immediately visible so debugging requires no reverse-engineering.
