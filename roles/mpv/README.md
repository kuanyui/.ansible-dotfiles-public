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
| `mpv.conf` | player defaults; `vo=wlshm` (see below) + `window-dragging=no` |
| `input.conf` | keybindings (left button is left to the gesture scripts) |
| `scripts/pointer-event.lua` | low-latency tap/double/long/drag detection (vendored, see below) |
| `scripts/touch-gestures.lua` | maps those events to seek / volume / speed / fullscreen (vendored) |
| `script-opts/pointer-event.conf` | wires pointer-event events -> touch-gestures; tap = pause, long = uosc menu |
| `script-opts/touch-gestures.conf` | tuning - `horizontal_drag=seek`, `seek_scale` (lower = finer) |

Uninstall: delete the files listed above from `~/.config/mpv/` (leave the rest
of the dir - mpv keeps user state like `watch_later/` there).

## Touch gestures

Vendored from christoph-heinrich's scripts (chosen for a SMOOTH seek - it does a
fast keyframe seek while you drag and a single exact seek when you stop, instead
of an exact seek every frame, which is what made the old script feel sluggish):

- [`mpv-pointer-event`](https://github.com/christoph-heinrich/mpv-pointer-event) `1.2.1` -> `scripts/pointer-event.lua`
- [`mpv-touch-gestures`](https://github.com/christoph-heinrich/mpv-touch-gestures) `1.1.0` -> `scripts/touch-gestures.lua` + both `script-opts/*.conf`

Gestures (with `horizontal_drag=seek`): horizontal drag = seek (proportional to
duration), vertical drag = speed (left half) / volume (right half), double-tap
zones = -10s / fullscreen / +10s, single tap = pause, long press = uosc menu (no
uosc -> harmless warning). The `.lua` files are kept verbatim; only the `.conf`
files are tuned (see their headers). `seek_scale=0.5` in `touch-gestures.conf`
tames overshoot if a full-screen drag jumps too far.

Security review (both `.lua`, this session): pure mpv playback-control API
(`seek`/`set volume`/`set speed`/property/timers/key-bindings/`assdraw`), all
command args numeric or hardcoded verbs; ZERO `os.*` / `io.*` / `subprocess` /
`run` / `load*` / `socket` / `package`. Safe.

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
| `scripts/touchscreen-seek.lua` + `touchscreen-drag-seek.lua` | replaced by christoph-heinrich's `pointer-event` + `touch-gestures` (smoother seek, proper touch/mouse split) - see the Touch gestures section above |
