# roles/centralize_lang_pkgs_dir

Redirects npm / pip / pipx / cargo / go global installs out of `~/.local/`
into a dedicated `~/.centralized-lang-pkgs/<tool>/` tree.

## Why

`~/.local/` is the XDG home for user-installed binaries, libraries, and
data: ansible drops scripts in `~/.local/bin/`, applications in
`~/.local/share/applications/`, app state in `~/.local/share/<app>/`, etc.
Letting npm / pip / pipx / cargo / go global installs share that tree
causes three problems:

1. **Hard to clean.** `rm -rf ~/.local/bin/` would also nuke ansible-managed
   launchers and your own scripts. You can't easily ask "what came from a
   package manager and what didn't?"
2. **Cross-tool collisions.** Different tools can install binaries with the
   same name. With everything in one bin/ dir, last-installer wins
   silently.
3. **AppArmor granularity.** A profile that grants
   `@{HOME}/.local/share/** r` opens user app state alongside third-party
   package-manager state. Splitting them lets a profile say "read
   third-party binaries (`~/.centralized-lang-pkgs/**`), but not user app state".

With this role enabled, `~/.local/` stays reserved for XDG and
ansible-managed dotfiles, and `~/.centralized-lang-pkgs/` is the dump for everything
installed by language-level package managers. To wipe all such installs
cleanly:

```
rm -rf ~/.centralized-lang-pkgs/
```

## Opt in

Not part of `apply-essentials-*`. Apply it explicitly via its dedicated
playbook:

```
make apply-centralize-lang-pkgs-dir
```

(No `setup_*` toggle - the role runs unconditionally when included; not
including it is the opt-out. The rc source line is guarded, so an
unapplied host is a no-op.)

## ivm guests: baseline, not opt-in

`roles/_shared_prebuilt_provision_assets` stages this role's output as the
`centralize-lang-pkgs-dir` dotfiles feature, and `ivm` pushes it into EVERY
guest as part of the baseline (`init` / `overwrite-dotfiles`). Thirdparty
recipes that install via npm / pip / pipx / cargo / go source the env file
at install time, so guest installs land in the same tree interactive guest
shells have on PATH. Exception: where nvm is installed, the templated rc
`unset`s `NPM_CONFIG_PREFIX` before loading it - nvm refuses to activate
with a foreign prefix (`nvm_die_on_prefix` in nvm.sh) and owns npm there.

## What this role configures

| Tool  | Env var(s)                          | Effect                                                       |
|-------|-------------------------------------|--------------------------------------------------------------|
| npm   | `NPM_CONFIG_PREFIX`                 | `npm install -g foo` writes to `~/.centralized-lang-pkgs/npm/{bin,lib}/` |
| pip   | `PYTHONUSERBASE` + `pip.conf`       | `pip install foo` defaults to `--user`, writes to `~/.centralized-lang-pkgs/pip/{bin,lib/...}/` |
| pipx  | `PIPX_HOME` + `PIPX_BIN_DIR`        | Isolated CLI tool venvs land in `~/.centralized-lang-pkgs/pipx/{venvs,bin}/` |
| cargo | `CARGO_HOME`                        | Cargo state + `cargo install foo` write to `~/.centralized-lang-pkgs/cargo/{bin,registry,...}/` |
| go    | `GOPATH`                            | `go install pkg/cmd@latest` writes to `~/.centralized-lang-pkgs/go/bin/` |

The role:

- Creates `~/.centralized-lang-pkgs/{npm,pip,pipx,cargo,go}/bin/` up front
- Deploys `~/.centralized-lang-pkgs/centralized-lang-pkgs.env.sh` with the env-var exports and
  PATH prepend
- Deploys `~/.config/pip/pip.conf` with `[install] user = true` so plain
  `pip install foo` redirects without remembering the `--user` flag (pip
  inside a venv ignores `user=` and writes to the venv as normal)
- The env file is sourced from `~/.zshrc` and `~/.bashrc` (the source line
  is always emitted by the `zsh` and `bash` roles, guarded by
  `[ -f ... ]`, so an opt-out is a no-op)

## Implementation notes

### PATH order

The env file prepends each tool's bin dir to `PATH`. Final order is:

```
~/.centralized-lang-pkgs/go/bin : ~/.centralized-lang-pkgs/cargo/bin : ~/.centralized-lang-pkgs/pipx/bin
 : ~/.centralized-lang-pkgs/pip/bin : ~/.centralized-lang-pkgs/npm/bin : <original PATH>
 : ~/.local/bin
```

Third-party installs win over distro defaults of the same name (common case:
`npm install -g typescript` providing `tsc`). `~/.local/bin` stays at the
tail as a legacy fallback for pre-existing manual installs.

### Idempotency

The env file uses a `CENTRALIZED_LANG_PKGS_ENV_LOADED` guard so re-sourcing (manual
`source ~/.zshrc`, nested shells) does not duplicate PATH entries.

### Scope limits

This role only redirects installs that happen **through a package manager
that respects these env vars**. It does NOT catch:

- Manual `cp foo ~/.local/bin/` placements
- Install scripts (`curl ... | sh`) that hard-code `~/.local/bin` or
  `/usr/local/bin`
- Anything you put in `~/.local/` by other means

Those still go where they were going. The role's promise is "package
managers stay out of `~/.local/`", not "nothing third-party ever touches
`~/.local/` again".

### Interactive shells only

The source line lives in `~/.zshrc` and `~/.bashrc`, both of which are
interactive-only by design (they early-return when `$PS1` is empty). Non-
interactive shells (cron, systemd user services, `.desktop` `Exec=` lines
invoking `sh -c`) will not see these env vars or the PATH prepend. If a
specific tool needs the redirect from a non-interactive context, set the
env var in that tool's own invocation environment.

## Adding a new tool

1. Append the export(s) and PATH prepend to
   `files/centralized-lang-pkgs.env.sh`
2. Add the new tool to the dir-creation loop in `tasks/main.yml`
3. If the tool needs a config file equivalent to `pip.conf`, drop it in
   `files/` and add a copy task

Each new entry should redirect through env vars where possible (env vars
travel with the shell; config files do not).
