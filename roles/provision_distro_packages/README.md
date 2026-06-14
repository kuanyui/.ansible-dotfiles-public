# roles/provision_distro_packages/

The **distro-package bundle registry**: named bundles in `defaults/` (`tools_basic`,
`gui_x11`, `cjk_input`, `desktop_lxqt`, ...), each a per-`ansible_os_family` overlay
(`__common__` + `Debian` / `Suse` / `RedHat`).

- **Host install**: `tasks/main.yml` installs the bundles toggled on by
  `provision_distro_packages_install_*`, via `roles/_install_distro_packages`
- **Guest / container**: serialized to the shared JSON by
  `roles/_shared_prebuilt_provision_assets`; read by `ivm` / `qvm` / `pvm` (`ivm provision <bundle>`)
- **Sibling**: `provision_thirdparty_software` (non-distro recipes)
- **Adding a bundle**: define it here AND in the producer's render dict (`tasks/main.yml`
  of `_shared_prebuilt_provision_assets`); completions auto-track
