### ============================================
### Prompts
### ============================================
# If not running interactively, don't do anything
[ -z "$PS1" ] && return

PS1="%F{gray}[%f%B%F{green}%n%f%b@%B%F{blue}%M%f%b%F{gray}:%f%B%F{red}%~%f%b%F{gray}]%F{yellow}%#%f%b (%D{%Y-%m-%d %H:%M:%S}) "
# PS1='%B%F{green}%n@%m%f:%F{blue}%~%F{yellow}%#%f%b '  # HOST ROOT
# PS1="%F{247}[%f%B%F{154}%n%f%b@%B%F{81}%M%f%b%F{247}:%f%B%F{231}%~%f%b%F{247}]%f"   # 256 colors

### ============================================
# [Backspace] don't seem / as part of word.
# https://stackoverflow.com/a/1438523/1244729
# This is probably fairly specific, but if this doesn't work, it may be because of the zsh-syntax-highlighting plugin: https://github.com/zsh-users/zsh-syntax-highlighting/issues/67. Make sure to source that plugin at the end of your zshrc.
### ============================================
autoload -U select-word-style
select-word-style bash

### ============================================
### History file configuration
### ============================================
[ -z "$HISTFILE" ] && HISTFILE="$HOME/.zsh_history"
[ "$HISTSIZE" -lt 50000 ] && HISTSIZE=50000
[ "$SAVEHIST" -lt 10000 ] && SAVEHIST=10000

### ============================================
### History command configuration
### ============================================
setopt extended_history       # record timestamp of command in HISTFILE
setopt hist_expire_dups_first # delete duplicates first when HISTFILE size exceeds HISTSIZE
setopt hist_ignore_dups       # ignore duplicated commands history list
setopt hist_ignore_space      # ignore commands that start with space
setopt hist_verify            # show command with history expansion to user before running it
setopt share_history          # share command history data

### ============================================
### Completions
### ============================================
# I don't know why this `compinit` is not required in
# `debian:bookworm` Docker image, but required in a real Debian
# Bookworm (debian 12) installation...
autoload -U compinit
compinit

zstyle ':completion:*' menu select=1 _complete _ignored _approximate  # Tab completion can use arrow keys to select now
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'       # Case insensitive tab completion
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"         # Colored completion (different colors for dirs/files/etc)

### ============================================
### Trivial options
### ============================================
setopt interactivecomments
setopt EXTENDED_HISTORY         # puts timestamps in the history
setopt MENUCOMPLETE   # Tab to auto complete command's arguments (e.g. git <TAB>)
setopt AUTO_CD    # cd to directory without cd command

### ============================================
### Alias
### ============================================
alias sz='source ~/.zshrc'
alias ta='if tmux attach-session -t 0;then;else tmux;fi'

alias ll='ls -al --color=auto '
alias ls='ls --color=auto '

alias ..='cd ..'
alias ...='cd ../../'
alias ....='cd ../../../'
alias .....='cd ../../../../'
alias ......='cd ../../../../../'

alias sc="systemctl"
alias jc="journalctl"
alias jc-clear="journalctl --vacuum-time=5d"   #  Delete journal logs which are older than 5 days

alias gl="git log --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit --graph"
alias gb="git branch"
alias gc="git checkout"
alias gs="git status"
alias gp="git pull"

alias set-lang-to-en='export LC_ALL=en_US.utf8; export LC_CTYPE=en_US.utf8; export LC_MESSAGES=en_US.utf8; export LANG=en_US.utf8; export LANGUAGE=en_US.utf8;'
alias set-lang-to-ja='export LC_ALL=ja_JP.utf8 LC_CTYPE=ja_JP.utf8 LC_MESSAGES=ja_JP.utf8 LANG=ja_JP.utf8 LANGUAGE=ja_JP.utf8;'

alias cccp='su -'  # Because `su -` is so fucking difficult to type. I'm extremely lazy.

function emacsx() {
    ('emacs' $@ > /dev/null 2>&1 &)
}

function dotfiles-public-update () {
    cd ~/.dotfiles-public/user/ &&
	git fetch --all &&
	git reset --hard origin/master &&
}

function apt-install-without-recommends () {
    sudo apt install --no-install-recommends $@
}

function apt-install-without-recommends-diff-dry-run () {
    if [ $UID -eq 0 ]; then
	echo "Please run as non-root for GUI (meld)"
	diff --width=$COLUMNS --suppress-common-lines --side-by-side --color <(apt-get install --dry-run $@) <(apt-get install --dry-run --no-install-recommends $@)
    else
	meld <(apt-get install --dry-run $@) <(apt-get install --dry-run --no-install-recommends $@)
    fi
}
### ============================================
### autosuggesstions (apt install zsh-autosuggestions)
### ============================================
if [ -f /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]; then
        source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

### ============================================
### Syntax Highlighting (apt-get install zsh-syntax-highlighting)
### [IMPORTANT] Please in the end of .zshrc
### ============================================
if [ -f /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]; then
        source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# PATH for pipx
PATH="${PATH}:${HOME}/.local/bin"
