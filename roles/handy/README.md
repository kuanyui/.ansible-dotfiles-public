# roles/handy/

Installs **Handy** - offline, push-to-talk speech-to-text that types the result into the
focused window - https://github.com/cjpais/Handy - on the HOST from its upstream GitHub release.

- **Type**: face role - `make apply-handy` / `make check-handy` (playbook `handy.yml`); needs sudo
- **Host-only**: needs a microphone, a desktop session and keystroke injection - nothing an
  `ivm` / `qvm` / `pvm` guest has, so it is NOT a `provision_thirdparty_software` recipe
- **Vars** (`defaults/main.yml`): `handy_version`, `handy_release_assets` (per-family filename +
  sha256), `handy_typing_tools_install_distro_packages`
- **Deploys**: the upstream package (`/usr/bin/handy`, `/usr/lib/Handy/`, `Handy.desktop`) + the
  keystroke-injection helpers; nothing under `~/.local/share/ansible-managed/`
- **AppArmor**: separate step - `roles/apparmor/tasks/handy.yml` (`make apply-apparmor`); ships as
  a complain-mode draft, promotion checklist in `roles/apparmor/TODO.md`

## Install path

| `ansible_os_family` | Asset | Installed via |
|---|---|---|
| `Suse` | `Handy-<version>-1.x86_64.rpm` | `zypper --non-interactive install --allow-unsigned-rpm <file>` |
| `Debian` | `Handy_<version>_amd64.deb` | `apt-get install --yes <file>` |

- Both resolve the package's declared deps from the distro repos (`libgtk-layer-shell0`, OpenBLAS,
  WebKitGTK 4.1, appindicator - on Debian 13 `libayatana-appindicator3-1` provides the
  `libappindicator3-1` the `.deb` asks for)
- Unsigned: upstream signs assets for its own updater only (minisign, a small signature tool,
  `.sig` files), not with GPG - hence `--allow-unsigned-rpm` and the pinned sha256 (`get_url`
  refuses a mismatch)
- Idempotent: `rpm --query` / `dpkg-query` version == `handy_version` -> nothing downloaded
- x86_64 only (asserted); upstream also ships aarch64 / arm64 assets - add them to
  `handy_release_assets` when needed
- The in-app updater cannot work here (the AppArmor profile denies its `pkexec` / `sudo` path):
  turn off update checks in Handy's settings, or launch with `HANDY_DISABLE_UPDATER=1`

## Upgrade

1. `defaults/main.yml`: set `handy_version`, then replace both `sha256` values (edit the version
   in the URLs first):

```
curl -L https://github.com/cjpais/Handy/releases/download/v0.9.8/Handy-0.9.8-1.x86_64.rpm | sha256sum
curl -L https://github.com/cjpais/Handy/releases/download/v0.9.8/Handy_0.9.8_amd64.deb | sha256sum
```

2. `make apply-handy`

## After install - per session type

Handy's own global shortcut (default `ctrl+space`) works on X11 only. On Wayland bind
`handy --toggle-transcription` to a desktop-wide shortcut yourself (KDE: System Settings >
Shortcuts > add a command). Typing the result into the focused window needs an external tool:

| Session | Tool Handy picks | Installed by this role |
|---|---|---|
| X11 | `xdotool` | yes |
| Wayland, not KDE / GNOME | `wtype` | yes |
| KDE / GNOME Wayland | `ydotool` (uinput) | openSUSE yes; Debian 13 has no package |

Handy would prefer `kwtype` on KDE Wayland (KDE's fake-input protocol), but no distro packages it.

### ydotool - two manual, security-relevant steps

`ydotool` talks to a daemon, `ydotoold`, which creates a virtual keyboard through `/dev/uinput`
(the kernel's user-space input-device interface). The openSUSE package ships a **user** unit, so
the daemon runs as you and needs write access to `/dev/uinput` - root-only by default.

1. Grant it through a dedicated group - NOT the `input` group, which also reads every
   `/dev/input/event*` (raw keystrokes) for any unconfined process running as you:

```
sudo groupadd --system uinput
sudo usermod --append --groups uinput "$USER"
printf 'KERNEL=="uinput", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"\n' | sudo tee /etc/udev/rules.d/80-uinput.rules
sudo udevadm control --reload && sudo udevadm trigger
```

   then log out and back in (group membership).

2. `systemctl --user enable --now ydotool`

Not automated on purpose: it widens who may inject input system-wide; decide it per host.

## Where Handy keeps its data

| What | Path |
|---|---|
| settings, models, recordings, history, logs | `~/.local/share/com.pais.handy/` (Tauri `app_data_dir`; the upstream README's `~/.config/com.pais.handy/` is not what Tauri 2 resolves on Linux) |
| Parakeet (ONNX) models | `~/.cache/huggingface/hub/` |
