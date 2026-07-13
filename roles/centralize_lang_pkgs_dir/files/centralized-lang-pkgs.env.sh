# =============================================================================
# MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY
# =============================================================================
# Lives at ~/.centralized-lang-pkgs/centralized-lang-pkgs.env.sh, sourced from ~/.zshrc and ~/.bashrc.
#
# Redirects npm / pip / pipx / cargo / go global installs out of ~/.local/{bin,
# share}/ and into ~/.centralized-lang-pkgs/<tool>/, so ~/.local/ stays reserved for XDG
# and ansible-managed dotfiles. To wipe all third-party installs cleanly:
#   rm -rf ~/.centralized-lang-pkgs/

# Idempotency guard: if this script has already run in the current shell, skip
# it. Prevents PATH duplication when something sources both ~/.zshenv and
# ~/.zshrc, or when the user manually re-sources.
[ -n "${CENTRALIZED_LANG_PKGS_ENV_LOADED:-}" ] && return
CENTRALIZED_LANG_PKGS_ENV_LOADED=1

_CENTRALIZED_LANG_PKGS="$HOME/.centralized-lang-pkgs"

# npm: `npm install -g foo` -> $NPM_CONFIG_PREFIX/{bin,lib}/
export NPM_CONFIG_PREFIX="$_CENTRALIZED_LANG_PKGS/npm"
PATH="$NPM_CONFIG_PREFIX/bin:$PATH"

# pip: `pip install --user foo` -> $PYTHONUSERBASE/{bin,lib/...}/
# `~/.config/pip/pip.conf` also sets `[install] user = true`, so the `--user`
# flag is redundant outside venvs. Inside a venv pip ignores user= and writes
# to the venv as normal.
export PYTHONUSERBASE="$_CENTRALIZED_LANG_PKGS/pip"
PATH="$PYTHONUSERBASE/bin:$PATH"

# pipx: isolated CLI tool venvs. Both data dir and bin dir relocated.
export PIPX_HOME="$_CENTRALIZED_LANG_PKGS/pipx"
export PIPX_BIN_DIR="$_CENTRALIZED_LANG_PKGS/pipx/bin"
PATH="$PIPX_BIN_DIR:$PATH"

# cargo: dir reserved even if Rust toolchain is not currently installed.
export CARGO_HOME="$_CENTRALIZED_LANG_PKGS/cargo"
PATH="$CARGO_HOME/bin:$PATH"

# go: defaults to ~/go when GOPATH is unset; redirect for consistency.
export GOPATH="$_CENTRALIZED_LANG_PKGS/go"
PATH="$GOPATH/bin:$PATH"

export PATH
unset _CENTRALIZED_LANG_PKGS
