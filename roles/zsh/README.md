# roles/zsh/

Deploys `~/.zshrc` (the login shell) + installs `zsh` and its plugins.

- **Deploys**: `.zshrc` - shared snippets (`shared_*`) from `roles/_shared_j2_snippets`;
  `override_os_family` picks the per-distro min-install helper (apt-min / zypper-min / dnf-min).
  Plus 3 vendored plugins (below).
- **Invoked by**: `include_role` - essentials (`playbooks/user.yml` / `root.yml`) +
  `_shared_prebuilt_provision_assets` dotfiles staging (which includes only
  `deploy-zsh-config.yml`, i.e. the `.zshrc` render - not the plugin payloads)
- **Caller sets**: `target_home` / `target_user` / `target_group` / `is_root` (+ optional `override_os_family`)

The prompt itself is a **font-free native-zsh PS1** (from `_shared_j2_snippets`), not a
framework theme - so nothing here needs a special font.

## Plugins - what each does

| Plugin | What it does |
|---|---|
| `zsh-autosuggestions` | As you TYPE, suggests the rest of the line in gray (a "ghost") from history. Right-arrow / End accepts it. |
| `zsh-history-substring-search` | Type a fragment, then Up / Down cycles only the history lines that **contain** it. Enter runs the shown one. |
| `zsh-syntax-highlighting` | Colors the command line live as you type (valid command green, unknown red, quotes / paths highlighted). Sourced **last**. |

### `autosuggestions` vs `history-substring-search` (easy to confuse - both touch history)

| | `autosuggestions` | `history-substring-search` |
|---|---|---|
| When | passive, **as you type** | active, **when you press Up / Down** |
| Shows | one gray inline prediction | replaces the line with a match, cycles through many |
| Match | **prefix** (line starts with what you typed) | **substring** (what you typed appears anywhere) |
| Use | right-arrow / End accepts | Up / Down cycle, Enter runs |

## Source + version (vendored, pinned)

Each plugin's runtime is vendored under `files/<plugin>/` at a pinned upstream release -
**audited as unmodified upstream**, minimal runtime only (no tests / docs / images). The
choice to vendor a fixed version (rather than a git submodule) keeps it auditable and
self-contained. Re-verify by diffing `files/<plugin>/` against the tag / commit below.

- `zsh-autosuggestions` **v0.7.1** - <https://github.com/zsh-users/zsh-autosuggestions>
  @ `e52ee8ca55bcc56a17c828767a3f98f22a68d4eb`
  (files: `zsh-autosuggestions.zsh` self-contained + `LICENSE`)
- `zsh-syntax-highlighting` **0.8.0** - <https://github.com/zsh-users/zsh-syntax-highlighting>
  @ `db085e4661f6aafd24e5acb5b2e17e4dd5dddf3e`
  (files: `zsh-syntax-highlighting.zsh` + `highlighters/*/<name>-highlighter.zsh` + `.version` + `.revision-hash` + `COPYING.md`; the vendored `.revision-hash` records the same commit pin)
- `zsh-history-substring-search` **v1.1.0** - <https://github.com/zsh-users/zsh-history-substring-search>
  @ `400e58a87f72ecec14f783fbd29bc6be4ff1641c`
  (file: `zsh-history-substring-search.zsh`; BSD license is in the file header, no separate `LICENSE`)

## Distro availability + install strategy

Checked Jun 2026 (local `apt-cache` on Debian 13 Trixie, Repology, software.opensuse.org).

| Plugin | Debian / Ubuntu | Fedora | openSUSE (default repos) |
|---|---|---|---|
| `zsh-autosuggestions` | pkg | pkg | none `*` |
| `zsh-syntax-highlighting` | pkg | pkg | none `*` |
| `zsh-history-substring-search` | none | none | none |

`*` openSUSE ships these only in the OBS devel project `shells:zsh-users`, **not** the
default OSS repo - a stock `zypper install` does not find them. So openSUSE effectively
provides none of the three.

**Strategy** (`.zshrc.j2`): source the distro copy under `/usr/share/...` first, else the
vendored copy.

- `install-zsh-from-distro-repo.yml` installs the two packaged plugins on Debian / RedHat
  (root only) - so those use the distro package (security updates, smaller).
- `deploy-zsh-plugins.yml` lays down all three vendored copies under
  `~/.local/share/ansible-managed/zsh/` as the fallback. openSUSE (no package) and
  `zsh-history-substring-search` (packaged nowhere) always use these.

Uninstall = `rm -rf ~/.local/share/ansible-managed/zsh/`.

## Not adopted

- **agnoster theme** (the old powerline prompt): needs a Powerline-patched / Nerd font -
  upstream README: *"you will need to install a Powerline-patched font for this theme to
  render correctly"* (it uses Private Use Area glyphs). Fragile across VMs / distros /
  terminals, no distro packages it, and the role already ships a font-free PS1. The prompt
  stays the existing PS1.
- **zsh-completions** (133 extra `_<cmd>` completion files): low value on VMs (most of
  those tools are not installed; zsh + the distro already ship a large completion set),
  and it would add 133 files to this public repo. Skipped.
