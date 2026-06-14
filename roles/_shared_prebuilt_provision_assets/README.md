# roles/_shared_prebuilt_provision_assets/

Internal `_` **producer** role (`include_role` only). Builds the shared, regenerable
provision-asset cache the non-ansible launchers read at provision time.

> Different from `roles/_shared_j2_snippets/` (build-time Jinja snippets). THIS role
> produces runtime DATA (JSON registries + dotfile trees).

**Output** `~/.local/share/ansible-managed/shared-prebuilt-provision-assets/`:

```
distro-package-groups.json   thirdparty-software.json
dotfiles/<feature>/{__common__,Debian,Suse,RedHat}/{home/user,root}/
```

- **Key scheme**: `__common__` (always) + the `ansible_os_family` value
  (`Debian`/`Suse`/`RedHat`) - the key IS the family, no mapping table
- **Consumers**: `ivm` now; `qvm`/`pvm` later. (Host reads the registry vars directly, not this.)
- **Render dict** (`tasks/main.yml`) = the ONE hand-maintained feature-key list
- **Lifecycle**: regenerable cache; the sanctioned shared top-level subdir (see CLAUDE.md).
  Sole consumer's uninstall removes it; ref-count once qvm/pvm co-produce
