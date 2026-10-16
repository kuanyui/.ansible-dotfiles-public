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
- **Provenance**: upstream CI binaries, not compiled here - what was verified, and the one input
  nobody can verify (the `.deb`'s ONNX Runtime), is in "Where the upstream binaries come from"
  below; "Build it from source on OBS instead?" holds the alternative

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

## Where the upstream binaries come from (checked 2026-10-16, v0.9.8)

This role installs upstream's prebuilt packages; nothing is compiled here. What was verified:

| Fact | Evidence |
|---|---|
| Built by GitHub Actions on GitHub-hosted runners, not on someone's laptop | `.github/workflows/release.yml` at tag `v0.9.8` (`workflow_dispatch`, the maintainer triggers it) runs `build.yml` with `no-cache: true`; the release API lists `github-actions[bot]` as uploader of every asset (published 2026-10-03) |
| Our pinned sha256 = what CI uploaded | equal to the release API `digest` of both assets; both files re-downloaded and re-hashed on 2026-10-16 |
| No provenance attestation (a signed statement naming the workflow that built an artifact) | GitHub's attestations API answers 404 for both digests |
| `.sig` assets | Tauri updater signatures (minisign); the private key is a repo secret, so they prove "signed by this project's CI", not an independent review |
| No reproducible build, no third-party audit, one maintainer | - |

### Build inputs of the Linux packages

| Input | Comes from | Verifiable? |
|---|---|---|
| Handy source | tag `v0.9.8` | public; we read the AppArmor-relevant parts only - this is not a malware audit |
| Rust crates | crates.io per `Cargo.lock` (the `hf-hub` fork is pinned to commit `9918f11`) | pinned, unaudited |
| npm packages (settings UI) | `bun.lock` | pinned, unaudited |
| whisper.cpp / ggml (`libtranscribe.so`, `libggml*.so`) | compiled in CI from the sources bundled in the `transcribe-cpp-sys` crate | traceable |
| ONNX Runtime 1.24.2 in the **`.rpm`** (built on `ubuntu-24.04`) | the `ort-sys 2.0.0-rc.12` build script downloads pyke's static build from `cdn.pyke.io`; its sha256 is pinned in the crate's `dist.txt` and checked during the build; linked statically into `handy` (47 MB, no `libonnxruntime*` under `/usr/lib/Handy/`) | yes - the trust anchor is pyke, the `ort` crate's maintainer |
| ONNX Runtime 1.24.2 in the **`.deb`** (built on `ubuntu-22.04`) | `/usr/lib/Handy/libonnxruntime.so.1` is downloaded by `build.yml` from `blob.handy.computer`, the maintainer's own host - **no checksum in the workflow, no build recipe in the repo** | **no** |
| Vulkan SDK, Rust `stable`, actions `@v5` / `@v0` | LunarG apt repo, floating versions | build toolchain, floating |

### The `.deb`'s ONNX Runtime is not Microsoft's binary

| | `.deb` ships (= the blob's content on 2026-10-16) | Microsoft `onnxruntime-linux-x64-1.24.2.tgz` |
|---|---|---|
| `libonnxruntime.so.1.24.2` size | 28,855,112 bytes | 22,065,056 bytes |
| sha256 | `873ed82ce0d898d6e588f31f415be11f9d9ac036984dcb9bbdc4e38058b1c8e4` | `ffc84d48e845cf0b562ba4ea5ca32aaafc0d4069019fef4f63095b307d0270ad` |
| compiler (`.comment` section) | GCC 11.4, Ubuntu 22.04 | GCC 14.2.1 |
| tarball packed | 2026-03-15 on a Mac (AppleDouble `._*` entries, owner `cj`) | Microsoft CI |

It looks like the maintainer's own rebuild on Ubuntu 22.04. Nothing public proves its contents.

### What follows for this role

- openSUSE (`.rpm`) carries no unverifiable blob. Debian (`.deb`) does.
- Mitigations in place: the sha256 pin freezes exactly the bytes inspected above; neither package has
  maintainer scripts; the install goes through the package manager; the AppArmor profile (promote
  it to enforce early); the in-app updater is blocked.
- On every `handy_version` bump, re-check the new tag's `build.yml` for the ONNX Runtime steps and
  re-hash what the packages ship (edit the version first):

```
dpkg-deb --fsys-tarfile Handy_0.9.8_amd64.deb | tar --extract --to-stdout ./usr/lib/Handy/libonnxruntime.so.1 | sha256sum
rpm2cpio Handy-0.9.8-1.x86_64.rpm | cpio --list 2>/dev/null | grep onnxruntime
```

The second line is expected to print nothing (the `.rpm` has no separate ONNX Runtime library).

## Build it from source on OBS instead? (evaluated 2026-10-16)

OBS = the openSUSE Build Service (build.opensuse.org): spec files built on isolated workers.
**Verdict: feasible as a personal home project, not as-is for Factory.** Expect 1-2 days to a first
working spec, then upkeep per upstream release (nine releases between July and October 2026).
Payoff: no upstream blob at all, the distro's ONNX Runtime, a GPG-signed repo, upgrades through
`zypper dup`; this role would shrink to "add repo + install".

| Need | Tumbleweed status (2026-10-16) | Note |
|---|---|---|
| No network during the build | hard rule: OBS user guide ch. 7.2 - build workers in secure mode have no external network access, always the case at build.opensuse.org | everything below is vendored or packaged |
| Rust crates offline | `obs-service-cargo` 7.2.2 (`cargo_vendor` -> `vendor.tar.zst`, git deps included) + `cargo-packaging` 1.5.0 (`%cargo_build`) | standard Rust packaging |
| Settings UI (`tsc && vite build`) offline | `obs-service-node_modules` 3.0.19 wants `package-lock.json`; upstream ships only `bun.lock` -> generate one (`npm install --package-lock-only --ignore-scripts`; the resolution may differ from upstream's) or copy the `bun_prefetch` approach of Factory's own `bun` 1.4.2 package | the build still executes npm-shipped prebuilt binaries (esbuild, rollup, Tailwind oxide); `@tauri-apps/cli` (also prebuilt) is avoidable: plain `cargo build` embeds `dist/` |
| ONNX Runtime | `onnxruntime-devel` 1.27.0 + `libonnxruntime1`; build with `ORT_LIB_LOCATION=/usr/lib64 ORT_PREFER_DYNAMIC_LINK=1` as the upstream Nix flake and nixpkgs do; `ort 2.0.0-rc.12` asks for C API 24 and a 1.27 runtime serves it (`GetApi` fails only on an older runtime; `ort` rejects only a minor version < 24) | removes both the blob and the pyke download |
| whisper.cpp / ggml + Vulkan | bundled in the `transcribe-cpp-sys` crate (1650 files, 161 GLSL shaders); needs `shaderc` (glslc), `spirv-headers`, `vulkan-headers`, `cmake`, `clang`; the only CMake downloads are the Windows OpenMP and AArch64 KleidiAI paths, both unreachable on x86_64 Linux | `ggml-devel` 0.5.0 exists, but transcribe.cpp builds its own ggml tree - a bundled copy, which Factory review asks about |
| GTK stack | `webkitgtk4-devel` 2.54 (the WebKitGTK 4.1 API), `libayatana-appindicator3-devel`, `gtk-layer-shell-devel`, `alsa-devel`, `libevdev-devel`, `openblas-common-devel` | all present |
| Packaging wrinkles | `handy` carries the rpath (library search path baked into the binary) `$ORIGIN/../lib/Handy` from upstream `build.rs`: install the ggml modules to `/usr/lib/Handy` or patch it for `/usr/lib64`; `.desktop` + icons by hand (no tauri-bundler); `_constraints` around 8 GB RAM, like the `onnxruntime` package | |
| Precedents | nixpkgs `handy` 0.9.6 (offline from-source, same ONNX Runtime approach, two releases behind upstream); AUR `handy` builds from source but with network; no OBS, COPR or Flathub package found | |

Debian hosts: OBS can target Debian too, but Rust + Node vendoring there was not evaluated; the
`.deb` path above would stay.
