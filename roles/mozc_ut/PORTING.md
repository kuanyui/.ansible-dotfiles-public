# mozc-ut on openSUSE - porting notes

Goal: **fcitx5-mozc-ut on an openSUSE host** (system-dictionary UT, to fix the import method's
>800MB RAM + bad candidate ordering). Primary path: **branch openSUSE's `mozc` package and overlay
the UT dictionary** - NOT a host/container from-scratch build.

Sources (all fetched, not from memory):
- **M17N/mozc** via OBS public API `api.opensuse.org/public/source/M17N/mozc` (rev 133, mozc
  **3.33.6133.102**). Its `_link` shows it is a plain branch of **openSUSE:Factory/mozc** -> this is
  the authoritative distro spec. `mozc.spec`, `fcitx-mozc-bazel-build.patch`, `use-system-python.patch`
  read in full.
- **AUR `mozc-ut-full` PKGBUILD** (mozc `3.33.6133.102.20260503`) - used only for the UT-merge logic.
- **fcitx/mozc** `src/MODULE.bazel` @ `a897811` - cross-checks the fcitx5 deps.

Note the version match: distro mozc `3.33.6133.102` == the AUR mozc-ut base. That matters - UT dict
POS ids are generated against a specific mozc version, so the UT `.txt` lines line up with this tree.

## 1. TL;DR

- Building mozc-ut = compiling **Mozc** (system dict); fcitx5 stays a distro package.
- fcitx5 plugin needs only **`fcitx5-devel`** (pkg-config `Fcitx5Core` + `Fcitx5Module`). **No
  `fcitx5-lua-devel` / `fcitx5-qt-devel`.** Confirmed by both the fcitx fork and M17N's own patch.
- **Bazel is NOT a blocker (correction).** Distro `mozc` builds with **`bazel8`** + a patched
  `MODULE.bazel` + vendored deps; it ignores fcitx/mozc's `.bazeliskrc` 9.0.2 (§7).
- **Best path (§9): `osc branch M17N mozc` (= Factory) and overlay UT.** The overlay is tiny (§8):
  one UT `Source` + one `cat` line in `%prep` + a rename. Everything hard is already solved upstream.
- osc/build runs on YOUR openSUSE host (KVM + OBS auth). Read-only inspection needs neither - the
  OBS public API is anonymous (that's how these notes were sourced).

## 2. fcitx5 deps: only `fcitx5-devel` (proof)

M17N's `fcitx-mozc-bazel-build.patch` adds to `src/MODULE.bazel`:
```
pkg_config_repository(
    name = "fcitx5",
    packages = ["Fcitx5Core", "Fcitx5Module"],
)
```
Identical to fcitx/mozc @ a897811. Both `.pc` files ship in **`fcitx5-devel`**. No qt/lua. mozc's GUI
(`mozc_tool`, `mozc_renderer`) needs **Qt6** (`pkgconfig(Qt6Core/Gui/Widgets)` in the spec), which is
Qt itself, NOT `fcitx5-qt-devel`.

## 3. Build/runtime deps (from M17N mozc.spec, fcitx5 subpackage)

| Purpose            | openSUSE package(s)                                  |
|--------------------|-----------------------------------------------------|
| Bazel              | **`bazel8`** (+ `unzip`, `zlib-devel`)              |
| fcitx5 plugin      | BuildRequires **`fcitx5-devel`**; Requires `fcitx5` |
| GUI tools/renderer | `pkgconfig(Qt6Core)`, `pkgconfig(Qt6Gui)`, `pkgconfig(Qt6Widgets)` |
| (ibus subpkg only) | `ibus-devel` - not needed for a fcitx5-only build   |

Runtime: `Requires: mozc = %{version}` + `mozc-gui-tools`. The `.so` is just the fcitx5 front end;
the engine (`mozc_server`) lives in the `mozc` subpackage.

## 4. How the spec builds fcitx5 (already done by M17N)

- `Source0`: google/mozc tarball. `Source20: fcitx-mozc-96fcec5b.tar.xz` = fcitx's `unix/fcitx{,5}`
  code, untarred over the tree; `Patch20` (the bazel-build patch above) wires it in.
- `%build`: `cd src; bazel build package "//unix/fcitx5:fcitx5-mozc.so" --repository_cache=../dependencies
  --registry=file:$(realpath ../bcr) --config oss_linux -c opt --force_pic ...`
- `package` is mozc's target group (server + gui + renderer + ibus + emacs); the fcitx5 `.so` is added
  explicitly. A fcitx5-only spin still gets `mozc_server`/`mozc_tool` via the `mozc` subpackage.

## 5. Install paths (lib64 - handled by the spec)

The spec uses `%{fcitx5_lib_dir} = %{_libdir}/fcitx5/` = **`/usr/lib64/fcitx5/`** on x86_64, and
`%{_libdir}/mozc` for the server/tool/renderer. So the lib64 concern is already correct in the spec
(macro-driven); a hand build must replicate `%{_libdir}`, not hardcode `/usr/lib`.

## 6. Bazel offline (the vendored-deps model)

M17N/mozc carries **static** vendored files (NO `_service` in the package - they are committed blobs):
- `dependencies.tar` (~45MB) -> `bazel --repository_cache=../dependencies`
- `bcr.tar.xz` (Bazel Central Registry subset) -> `bazel --registry=file:.../bcr`
- `use-system-python.patch` registers `/usr/bin/python3` as the bazel py toolchain (no network python).
- `%prep` also appends bazel8-aligned module versions:
  `bazel_dep(name="rules_java", version="8.14.0")` + `zlib 1.3.1.bcr.5` (Bazel 8.4 built-ins).

**Key for UT:** the UT overlay only appends text to a dictionary file; it does NOT touch the bazel
dependency graph. So `dependencies.tar` + `bcr.tar.xz` are **reused as-is** - the hardest artifact is
free. (Regenerating them, if ever needed, is what `openSUSE/obs-service-bazel_repositories` is for.)

## 7. Bazel version: why bazel8 is fine (correction)

fcitx/mozc's `src/.bazeliskrc` pins `USE_BAZEL_VERSION=9.0.2` via bazelisk. **The distro does not
follow that.** M17N/Factory builds with system **`bazel8`**, aligning module versions in `%prep`
(rules_java 8.14.0, zlib 1.3.1.bcr.5) and pointing bazel at the vendored registry/cache. So:
- OBS path: `bazel8` (distro package) + vendored deps. No bazelisk, no 9.0.2, no network.
- Only a from-scratch host/container build that follows upstream literally would need bazelisk 9.0.2 -
  and there's no reason to, given the working distro spec.

## 8. The UT overlay (the entire delta over M17N/mozc)

Everything else is inherited. The UT-specific changes:

1. Regenerate a merged UT dict (offline, when refreshing dictionaries): run
   `utuhiro78/merge-ut-dictionaries` over `mozcdic-ut-*` (jawiki/neologd/place-names/...) to produce a
   single `mozcdic-ut.txt` in **mozc build format** (`reading \t lid \t rid \t cost \t word`). Pin it
   by date. (The AUR PKGBUILD's `prepare()` is the reference; note it also `echo '' >
   unsuitable_words.txt` to disable the profanity filter - a choice, not required.)
2. Add it as a Source and merge it in `%prep`, AFTER `%setup` + all patches, BEFORE `%build`:
   ```
   Source30:  mozcdic-ut.txt
   ...
   # %prep, last step:
   cat %{SOURCE30} >> src/data/dictionary_oss/dictionary00.txt
   ```
3. Rename / relate the package: `Name: mozc-ut`, or keep `mozc` and add
   `Provides: mozc-ut = %{version}`; add `Provides/Obsoletes` vs stock mozc only if it must replace it.

Reused unchanged: `bazel8`, `dependencies.tar`, `bcr.tar.xz`, `Patch20` (fcitx5 wiring),
`use-system-python.patch`, all install/lib64/i18n logic. That is the whole point of branching Factory.

## 9. Where to build

| Option | Host clean | Auto-rebuild on TW update | Effort | Verdict |
|---|---|---|---|---|
| A. host build | dirty (toolchain stays) | no | low | rejected (user won't pollute host) |
| B. container/incus build | clean (copy artifacts to host) | no (manual) | medium | only for a quick local "does it fix RAM/order?" trial |
| C. **OBS: branch M17N/mozc + UT overlay** | cleanest (`zypper install`) | **yes** | low-ish (spec delta is tiny, §8) | **recommended** |

C is now clearly best: the delta over a working, official spec is minimal (§8), OBS rebuilds against
current Tumbleweed (fixes the rolling-ABI drift a hand-built artifact suffers), and the host just adds
a repo + installs. B is a throwaway sanity check at most.

**Decoupling:** C lives in its OWN OBS project / git package (`osc branch M17N mozc`), NOT in this
dotfiles repo (from-source compiling clashes with the repo's package-only philosophy). dotfiles then
consumes it as a thin "add repo + `zypper install mozc-ut`" bundle via the existing provision
mechanism. **This PORTING.md is the seed for that standalone package.**

## 10. Risks / open items

- **OBS build limits:** the UT dict adds ~1M+ entries to the system dictionary -> longer build, more
  RAM, bigger artifact. OBS workers have time/memory caps; a giant merged dict may time out or OOM.
  Mitigate by trimming which `mozcdic-ut-*` subdicts are merged, or requesting bigger constraints.
- **UT dict freshness:** jawiki-derived entries drift; refreshing means regenerating `mozcdic-ut.txt`
  (step 8.1) and bumping its pin. Not automatic.
- **POS-id coupling:** the UT `.txt` must match the mozc version's POS ids. Fine now (both 3.33.6133.102);
  re-verify whenever Factory bumps mozc.
- **Division of labor:** read-only inspection = anonymous OBS public API (done here). `osc branch` /
  `osc build` / `osc commit` = your openSUSE host, your OBS credentials, local KVM.
