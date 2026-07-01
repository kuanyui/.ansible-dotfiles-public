# Distro AppArmor profiles break after an update: the `.rpmnew` trap

Status: REFERENCE (diagnosis + fix runbook). Not code. Written 2026-07-01, from a live incident
(`QtWebEngineProcess` + `systemd-coredump` denied on one openSUSE Tumbleweed host, another host clean).

## TL;DR

After a distro package update, a GUI app (e.g. `syncthingtray`, anything embedding QtWebEngine) is
suddenly AppArmor-denied and will not start. Cause: the distro shipped a NEW version of that app's
profile as `/etc/apparmor.d/<name>.rpmnew`, but the OLD profile is still what the kernel enforces,
and the `.rpmnew` is **never loaded automatically**. Fix: adopt the `.rpmnew`, reload.

This is NOT about the profiles this role manages - ours are all `local_*` and are immune (section 5).

## 1. What `.rpmnew` is

Distro profiles under `/etc/apparmor.d/` are packaged `%config(noreplace)` ("this is a config file;
on upgrade do not clobber a modified one"). On update, if the on-disk file differs from the packaged
checksum, RPM keeps yours and parks the new one alongside:

| File | What it is | Enforced? |
|---|---|---|
| `/etc/apparmor.d/<name>` | your OLD, on-disk-modified profile | **yes** (this is the problem) |
| `/etc/apparmor.d/<name>.rpmnew` | the NEW vendor profile, sitting inert | no |

(Contrast `.rpmsave`: for plain `%config` without `noreplace`, RPM installs the new file and saves
your old one as `.rpmsave`. AppArmor profiles use `noreplace`, so you get `.rpmnew`.)

## 2. Why the `.rpmnew` never takes effect (filename vs profile name)

The common objection: "AppArmor keys profiles by the profile NAME declared inside the file, not by
the filename - so the `.rpmnew` should load too." Half right. Two different layers:

| Layer | Decided by | Keyed on |
|---|---|---|
| Which files get compiled + loaded | userspace `apparmor_parser` (run over `/etc/apparmor.d/` by `apparmor.service`) | **filename** |
| What the loaded profile is keyed as in the kernel | kernel | **profile name** |

Name-keying is the SECOND layer - it happens only after a file is chosen and compiled. The `.rpmnew`
never reaches it, because it is dropped at the FIRST layer: the directory loader skips a filename
blacklist, and `.rpmnew` is on it. So its `profile <name> { ... }` declaration never reaches the
kernel; only the un-suffixed old file is enforced.

### Where the blacklist is defined

- **Authoritative reference:** `apparmor_parser(8)` man page. It lists the exact suffixes.
- **Source:** function `is_blacklisted()` in AppArmor's parser (`parser/parser_main.c`), called from
  the directory-walk callbacks. It is applied **only during directory traversal**.
- **The list** (skipped when `apparmor_parser` scans a directory), plus any dot file:

  ```
  *.dpkg-new  *.dpkg-old  *.dpkg-dist  *.dpkg-bak  *.dpkg-remove
  *.pacsave   *.pacnew
  *.rpmnew    *.rpmsave
  *.orig      *.rej       *~
  ```

- **Key consequence (the test lever):** the blacklist is directory-scan only. Handing the file to
  the parser by an **explicit path** bypasses it, so `apparmor_parser --replace <name>.rpmnew` DOES
  load it (used in section 4.1). Boot and `systemctl reload apparmor` use directory-scan, so they
  never touch a `.rpmnew`.

## 3. How to recognise it in the audit log

`AVC` (Access Vector Cache - the kernel audit record for a security-module allow/deny) lines like
`apparmor="DENIED" ... profile=<name> ... name=/usr/lib64/...`, denying **basic library loads**:
`/etc/ld.so.cache`, `/usr/lib64/`, `libFoo.so.<ver>`, `/usr/lib64/glibc-hwcaps/x86-64-v{2,3}/`
(`glibc-hwcaps/` = glibc's per-CPU-microarchitecture library search dirs; `v2`/`v3` are x86-64 levels).

A profile denying *basic libs* is the tell: it is stale versus the current library layout (new Qt /
glibc / systemd version, so new versioned library filenames) that the vendor's newer profile already
covers.

- **Cascade seen in this incident:** `QtWebEngineProcess` denied its own libs -> crashed -> kernel
  invoked `systemd-coredump` to collect the core -> `systemd-coredump`'s profile is ALSO stale ->
  it too was denied `libsystemd-shared-<ver>.so`. Two stale profiles, one root cause.
- **"One host has the AVC, another does not":**
  - likely: the clean host took the update with no local divergence -> no `.rpmnew`, new profile
    enforced.
  - also possible: the other host runs SELinux (the default on new openSUSE installs), so it emits
    no AppArmor AVCs at all. Confirm per host: `aa-status` (AppArmor) vs `sestatus` (SELinux).

## 4. Fix runbook (run on the affected host; `sudo` will prompt)

Three levers, light to heavy.

### 4.1 Test only - non-destructive, auto-reverts

```
sudo apparmor_parser --replace /etc/apparmor.d/<name>.rpmnew
```

- `--replace` reads the profile name from inside the file and swaps the in-kernel profile of that
  name, regardless of the `.rpmnew` filename.
- Launch the app. Works -> go to 4.2. Worse -> `sudo systemctl reload apparmor` reverts it (the
  directory scan reloads the old file and ignores the `.rpmnew`).
- This is temporary: the next full reload / reboot loads the old file back, so make it permanent.

### 4.2 Adopt one permanently

```
sudo mv /etc/apparmor.d/<name>.rpmnew /etc/apparmor.d/<name>
sudo systemctl reload apparmor
```

### 4.3 Adopt many at once - use `rpmconf`, do not script it

`rpmconf` (install: `sudo zypper install rpmconf`) is the standard RPM-distro tool for
`.rpmnew` / `.rpmsave` / `.rpmorig`: per file it lets you keep yours, take the new one, diff, or
merge, then deletes the leftover. This is how RPM-distro users manage these - no custom script needed.

Scope it to the AppArmor package. Preview, then accept every vendor version (safe here - this role
never customises distro profiles, section 5, so nothing of yours is lost), then reload:

```
sudo rpmconf --owner=apparmor-profiles --diff
```

```
sudo rpmconf --owner=apparmor-profiles --unattended=use_maintainer
sudo systemctl reload apparmor
```

- `--owner=<pkg>` = one package; `--all` = every package. A profile shipped by a different package
  (e.g. a `systemd-coredump` profile) needs that package's name, or use `--all`.
- `--unattended=use_maintainer` = take the `.rpmnew` (vendor) version; `use_your` = keep yours; omit
  it for an interactive keep/replace/diff/merge prompt. `--frontend=meld` (or `vimdiff`, `kdiff3`)
  picks the merge UI.
- FOOTGUN: `--all --unattended=use_maintainer` overwrites YOUR edits to every config on the system
  (`sshd_config`, ...), not just AppArmor. For a system-wide pass use interactive `sudo rpmconf --all`
  and decide per file. `--unattended` is only safe scoped to a package you never hand-edit.

Dependency-free fallback (no `rpmconf`), scoped to `/etc/apparmor.d/` - every `.rpmnew` there is a
distro profile, ours are `local_*` and never get one (section 5):

```
for f in /etc/apparmor.d/*.rpmnew; do echo "=== ${f} ==="; diff "${f%.rpmnew}" "${f}"; done
for f in /etc/apparmor.d/*.rpmnew; do sudo mv "${f}" "${f%.rpmnew}"; done
sudo systemctl reload apparmor
```

### 4.4 List every pending `.rpmnew` system-wide

They accumulate everywhere, not just AppArmor:

```
cat /var/adm/rpmconfigcheck
```

```
sudo rpmconf --all --test
```

`/var/adm/rpmconfigcheck` is written by openSUSE's `rpmconfigcheck` timer (it scans the RPM database
for unresolved `.rpmnew` / `.rpmorig` / `.rpmsave`); it is only as fresh as the last timer run.
`rpmconf --all --test` computes the list live.

## 5. Why this role's profiles are immune

| | Filename shape | Owned by | Gets `.rpmnew`? |
|---|---|---|---|
| Distro profile | bare name (`keybase`, `QtWebEngineProcess`, ...) | RPM package `apparmor-profiles` | yes, on update |
| This role's profile | `local_*` prefix | this Ansible role (RPM does not own it) | **never** |

Two guarantees:

1. RPM never writes `.rpmnew` for a file it does not own, so `local_*` files are untouched by
   package updates.
2. The role's mode step (`aa-enforce` / `aa-complain`, which **rewrite** a profile's `flags`) is
   scoped strictly to `local_*` - see `tasks/_install.yml` (the batched `aa-*` invocation builds its
   path list only from `apparmor_static_profiles` + `apparmor_template_profile_names`). It never
   rewrites a distro profile.

The verbose `local_*` naming convention (see `roles/apparmor/CLAUDE.md`, "AppArmor profile naming")
IS this immunity: our namespace never collides with a distro profile name, and RPM's config-conflict
machinery never engages on our files.

## 6. Open anomaly (diagnostic only - not resolved)

On the affected host, MANY distro profiles had diverged (all carried a `.rpmnew`) although they were
never hand-edited. `.rpmnew` only appears when on-disk != packaged checksum, so SOMETHING modified
them. Confirmed NOT this role (section 5). To find what, on the host:

```
rpm --verify apparmor-profiles
```

```
diff /etc/apparmor.d/<name> /etc/apparmor.d/<name>.rpmnew
```

- diff shows only a `flags=(complain)` line -> a mode tool (`aa-complain`, YaST AppArmor) set the
  mode across profiles at some point (note: complain mode logs `ALLOWED`, not `DENIED`; the incident
  log showed `DENIED`, so the enforced profiles are NOT in complain mode - lean toward the next case).
- diff shows real rule differences -> the vendor changed the rules and the old copy was not cleanly
  replaced.

If a bulk of `.rpmnew` reappears after the NEXT `apparmor-profiles` update, a recurring rewriter is
the real bug - hunt it then; adopting `.rpmnew` only treats the symptom.

## References

- `apparmor_parser(8)`, blacklist + directory-load behavior:
  https://manpages.opensuse.org/Tumbleweed/apparmor-parser/apparmor_parser.8.en.html
- `is_blacklisted()` implementation: `parser/parser_main.c` in https://gitlab.com/apparmor/apparmor
- `.rpmnew` vs `.rpmsave` / `%config(noreplace)`: https://www.cl.cam.ac.uk/~jw35/docs/rpm_config.html
- `rpmconf(8)` (the standard `.rpmnew` handler): https://manpages.opensuse.org/Tumbleweed/rpmconf/rpmconf.8.en.html ;
  upstream https://github.com/xsuchy/rpmconf
- openSUSE `rpmconfigcheck` (populates `/var/adm/rpmconfigcheck`): shipped in the `rpm` package
- openSUSE default LSM change (AppArmor -> SELinux on new installs):
  https://9to5linux.com/opensuse-replaces-apparmor-with-selinux-on-new-tumbleweed-installations
- Role enforce/complain scope: `roles/apparmor/tasks/_install.yml`
- Naming convention (the immunity): `roles/apparmor/CLAUDE.md`, section "AppArmor profile naming"
- Default enforce mode: `roles/apparmor/defaults/main.yml` (`apparmor_profile_mode: enforce`)
</content>
</invoke>
