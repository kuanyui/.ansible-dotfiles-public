# mpv role

Deploys mpv player config to `~/.config/mpv/`. Migrated from the legacy stow
dotfiles `mpv/` package, with sensitive bits dropped (see table below).

Config-style face role (standard dotfile location, like `zsh` / `emacs`) - no
`~/.local/share/ansible-managed/` namespace dir.

Gate: `setup_mpv` (default `false` in `group_vars/all.yml`). Dedicated entry:
`make apply-mpv` / `make check-mpv` (bypasses the gate via `playbooks/mpv.yml`).

## Deployed files

| File | Purpose |
| --- | --- |
| `mpv.conf` | player defaults; `vo=wlshm` (see below) |
| `input.conf` | keybindings |
| `scripts/touchscreen-seek.lua` | double-tap left/center/right = seek/pause |
| `scripts/touchscreen-drag-seek.lua` | drag gestures: left-drag = seek (horizontal) / volume (vertical) with inertia, middle-drag = speed. Pairs with `window-dragging=no`. Toggle at runtime with `script-message toggle` |

Uninstall: delete the files listed above from `~/.config/mpv/` (leave the rest
of the dir - mpv keeps user state like `watch_later/` there).

## Why `vo=wlshm`

Plain `mpv` runs confined by the no-GPU AppArmor profile `local_pathbased_mpv`
(`roles/apparmor`): X11 (xauth) and every `/dev/dri` node are denied. The mpv
default `vo=gpu` then fails all GPU contexts and plays audio with NO window.

`wlshm` = Wayland shared-memory software output. Needs neither X11 nor a DRM
node, so it works inside the confinement.

Hardware playback: launch via `ansible-mpv-gpu.desktop`
(`local_attachmentless_mpv_gpu` profile). It must pass `--vo=gpu` to override
this default AND the profile needs a card-node grant - deferred, see `TODO.md`.

## Dropped vs the original stow package

| Dropped | Why |
| --- | --- |
| per-machine conditional profiles | hostname fragments = device fingerprint in a public repo; mechanism broken on Linux (HOSTNAME env unset for GUI launches). Their useful payloads survived unconditionally: `window-dragging=no` (touch: one-finger drag flung the window; KWin title bar / Meta+drag still move it) and a commented-out `input-ipc-server` |
| `scripts/lib-for-conf.lua` | only served those profiles; printed a log line every launch |
| `input.conf` `p` binding | personal helper path from the macOS era - leaked home layout, dead on Linux |
| `sub-ass-force-style` | renamed upstream; carried as `sub-ass-style-overrides` |
| `KDE_global_shortcuts_examples.sh` | reference-only socat snippets, unused; the IPC socket they drive stays commented out. The socat usage pattern is preserved inline in `mpv.conf`'s IPC comment, so nothing is lost |
