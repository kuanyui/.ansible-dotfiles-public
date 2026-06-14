# roles/_shared_prebuilt_provision_assets/

Internal `_`-prefixed **producer** role (invoked via `include_role` only - no
paired playbook, no Makefile target). It builds the SHARED, regenerable
provision-asset cache that every provisioning backend reads at provision time.

> Not to be confused with [`roles/_shared_j2_snippets/`](../_shared_j2_snippets/), which holds shared
> *Jinja shell-rc fragments* (build-time template snippets). THIS role produces
> *runtime data* (JSON registries + staged dotfile trees) consumed by the
> non-ansible launchers.

## Output

`~/.local/share/ansible-managed/shared-prebuilt-provision-assets/`:

```
distro-package-groups.json   # provision_distro_packages registry, serialized
thirdparty-software.json     # provision_thirdparty_software registry, serialized
dotfiles/
  <feature>/                 # bash / tmux / zsh / emacs (== the JSON key where it overlaps)
    __common__/{home/user,root}/   # always-applied bucket
    Debian/{home/user,root}/       # per-ansible_os_family overlay
    Suse/{home/user,root}/
    RedHat/{home/user,root}/
```

## Why it exists

`provision_distro_packages` + `provision_thirdparty_software` + the guest dotfiles
are ONE source of truth. The host reads the registry VARS directly (ansible), but
the non-ansible launchers (`ivm`, later `qvm` / `pvm`) have no ansible at provision
time - so this role snapshots both registries to JSON + stages the feature-first
dotfiles tree ONCE, host-side, into a dir they all read.

## Key scheme

`__common__` (always applied) + the exact `ansible_os_family` values `Debian` /
`Suse` / `RedHat`. The family key IS the ansible_os_family value, so consumers
index it directly - no name-mapping table. Family split (audited per file):
bash / tmux / emacs are family-independent (`__common__`); `.zshrc` is per-family
(its min-install helper differs: apt-min / zypper-min / dnf-min, via
`override_os_family`). `user` vs `root` differ by the `is_root` render.

## Consumers

| Consumer | Reads it? |
|---|---|
| host (apply) | NO - reads the registry vars directly |
| `ivm` (`roles/vm_incus`) | YES - JSON + push dotfiles via `incus exec` |
| `qvm` (`roles/vm_quickemu`) | planned (Phase 2) - via QGA `guest-exec` |
| `pvm` (`roles/vm_podman`) | planned (Phase 3) - `Dockerfile` reads at image build |

## The render dict = the one feature-key list

`tasks/main.yml`'s render dict is the ONLY hand-maintained list of feature keys
(it serializes both registries to JSON). Adding a bundle / recipe = define it in
the owning registry's `defaults/` AND add it to that render dict. Shell
completions auto-track (they read the rendered JSON at runtime) - no completion
edit needed for a new bundle.

## Lifecycle (shared cache)

A REGENERABLE cache - any consumer's apply rebuilds it; it holds no unique state.
It is a TOP-LEVEL `ansible-managed/` subdir owned by this producer and consumed by
several face roles: the sanctioned exception to "one hyphenated subdir per face
role" (see the top-level `CLAUDE.md` "Shared prebuilt-asset dirs"). While `ivm` is
the SOLE consumer, its uninstall removes the cache; once `qvm` / `pvm` co-produce
it, removal must become conditional / ref-counted so one consumer's uninstall does
not delete a cache the others still need.
