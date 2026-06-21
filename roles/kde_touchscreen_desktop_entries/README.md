# kde_touchscreen_desktop_entries role

Deploys a small set of KDE application-menu entries the user made for **touchscreen
use** - screen rotation, screenshots, and a display-settings shortcut - plus the
`rotate_screen` helper the rotation entries call. Migrated from the legacy stow
`xdg-desktop-screen-rotation` package (the helper came from the stow `scripts` package).

Config-style role (standard XDG locations, like `mpv`) - no
`~/.local/share/ansible-managed/` namespace dir.

Entry point: `make apply-kde-touchscreen-desktop-entries` / `make check-kde-touchscreen-desktop-entries`.
No global gate (run the target/playbook when a host wants it).

## Deployed files

Helper script:

| File | Purpose |
| --- | --- |
| `~/.local/bin/rotate_screen` | rotate helper - Wayland via `kscreen-doctor`, X11 via `xrandr` + `xinput` |

Menu entries (in `~/.local/share/applications/`, `ansible_`-prefixed per the repo convention
for ansible-managed desktop files; grouped `ansible_display_*` / `ansible_take_screenshot_*`):

| File | Menu name | Action |
| --- | --- | --- |
| `ansible_display_horizontal.desktop` | Horizontal | `rotate_screen 0` (normal) |
| `ansible_display_vertical.desktop` | Vertical | `rotate_screen 1` (left) |
| `ansible_display_toggle_rotation.desktop` | Toggle Rotation | `rotate_screen` (no arg = cycle) |
| `ansible_display_settings.desktop` | KDE Display Settings | `systemsettings kcm_kscreen` |
| `ansible_take_screenshot_full.desktop` | Screenshot (Full) | `spectacle` full -> XDG Pictures `/Screenshots` |
| `ansible_take_screenshot_rectangle.desktop` | Screenshot (Rectangle) | `spectacle` region -> XDG Pictures `/Screenshots` |

Screenshots save to `$(xdg-user-dir PICTURES)/Screenshots` - the user's real XDG pictures
directory resolved at click time, NOT a hardcoded `~/Pictures` (it may be relocated/localized
via `~/.config/user-dirs.dirs`). The role resolves the same dir at deploy and `mkdir`s
`<XDG PICTURES>/Screenshots` so it exists.

Uninstall:

    rm ~/.local/share/applications/ansible_display_*.desktop \
       ~/.local/share/applications/ansible_take_screenshot_*.desktop \
       ~/.local/bin/rotate_screen

## Runtime dependencies (NOT installed by this role)

Provided by the KDE desktop, like the original stow package assumed:

| Tool | Used by |
| --- | --- |
| `kscreen-doctor`, `jq` | rotation under Wayland |
| `xrandr`, `xinput` | rotation under X11 |
| `spectacle` | the two screenshot entries |
| `xdg-user-dir` (`xdg-user-dirs` pkg) | resolves the screenshots target dir (deploy time + click time) |
| `systemsettings` | the display-settings entry |

## Ported as-is (known issues carried over verbatim)

The helper is a faithful copy of the user's tested script; only a `MANAGED BY ANSIBLE`
header was added (and the `~/.scripts` path moved to `~/.local/bin`). Pre-existing
quirks were deliberately NOT "fixed" during the port:

- The rotation action `case` tests `[ -n $WAYLAND_DISPLAY ]` **without quotes**, which
  is always true - so the X11 branch never runs. Fine on Wayland (the user's setup),
  broken on pure X11. The source also marks its X11 detection "not test".
- `kscreen-doctor output.1.rotation.*` hardcodes output index `1`.
- The original short CLI flags (`spectacle -b -f -o`, `kscreen-doctor -j`, ...) were kept
  verbatim rather than expanded to long form, to avoid altering tested commands.

Tell me if you want any of these fixed.

## Changed vs the original stow package

| Change | Why |
| --- | --- |
| helper path `~/.scripts/rotate_screen` -> `~/.local/bin/rotate_screen` | repo convention (on PATH); `.desktop` `Exec` updated to the absolute path |
| `.desktop` `Exec` `${HOME}/...` -> rendered absolute `{{ target_home }}/...` | a graphical launch does not inherit the interactive-shell PATH; matches the `roles/apparmor` Telegram launcher pattern |
| Japanese `GenericName` on the screenshot entries -> English | repo rule: all strings in English |
| added `MANAGED BY ANSIBLE` headers | repo rule for `~/.local/bin` + `~/.local/share/applications` files |
| `.desktop` filenames -> `ansible_display_*` / `ansible_take_screenshot_*` | repo convention: `ansible_`-prefixed for ansible-managed desktop entries (cf. `ansible_telegram`, `ansible_aa_firefox_*`); also keeps them distinct from the legacy stow names, so the migration guard can detect leftover symlinks |
| screenshot dir hardcoded `$HOME/Pictures/Screenshots` -> `$(xdg-user-dir PICTURES)/Screenshots` | respects the user's real XDG pictures dir instead of assuming `~/Pictures`; the role also `mkdir`s it (spectacle `-o` needs the dir to exist) |

No private data was carried over: the source held no username and no real home paths
(the screenshots dir is resolved at runtime via `xdg-user-dir PICTURES`, not baked in).
