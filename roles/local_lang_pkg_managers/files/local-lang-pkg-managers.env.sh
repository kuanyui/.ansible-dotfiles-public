# =============================================================================
# MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY
# =============================================================================
# Lives at ~/.local-lang-pkg-managers/local-lang-pkg-managers.env.sh, sourced from ~/.zshrc and ~/.bashrc.
#
# Redirects npm / pip / pipx / cargo / go global installs out of ~/.local/{bin,
# share}/ and into ~/.local-lang-pkg-managers/<tool>/, so ~/.local/ stays reserved for XDG
# and ansible-managed dotfiles. To wipe all third-party installs cleanly:
#   rm -rf ~/.local-lang-pkg-managers/

# Idempotency guard: if this script has already run in the current shell, skip
# it. Prevents PATH duplication when something sources both ~/.zshenv and
# ~/.zshrc, or when the user manually re-sources.
[ -n "${LOCAL_LANG_PKG_MANAGERS_ENV_LOADED:-}" ] && return
LOCAL_LANG_PKG_MANAGERS_ENV_LOADED=1

_LOCAL_LANG_PKG_MANAGERS="$HOME/.local-lang-pkg-managers"

# npm: `npm install -g foo` -> $NPM_CONFIG_PREFIX/{bin,lib}/
export NPM_CONFIG_PREFIX="$_LOCAL_LANG_PKG_MANAGERS/npm"
PATH="$NPM_CONFIG_PREFIX/bin:$PATH"

# pip: `pip install --user foo` -> $PYTHONUSERBASE/{bin,lib/...}/
# `~/.config/pip/pip.conf` also sets `[install] user = true`, so the `--user`
# flag is redundant outside venvs. Inside a venv pip ignores user= and writes
# to the venv as normal.
export PYTHONUSERBASE="$_LOCAL_LANG_PKG_MANAGERS/pip"
PATH="$PYTHONUSERBASE/bin:$PATH"

# pipx: isolated CLI tool venvs. Both data dir and bin dir relocated.
export PIPX_HOME="$_LOCAL_LANG_PKG_MANAGERS/pipx"
export PIPX_BIN_DIR="$_LOCAL_LANG_PKG_MANAGERS/pipx/bin"
PATH="$PIPX_BIN_DIR:$PATH"

# cargo: dir reserved even if Rust toolchain is not currently installed.
export CARGO_HOME="$_LOCAL_LANG_PKG_MANAGERS/cargo"
PATH="$CARGO_HOME/bin:$PATH"

# go: defaults to ~/go when GOPATH is unset; redirect for consistency.
export GOPATH="$_LOCAL_LANG_PKG_MANAGERS/go"
PATH="$GOPATH/bin:$PATH"

export PATH
unset _LOCAL_LANG_PKG_MANAGERS
