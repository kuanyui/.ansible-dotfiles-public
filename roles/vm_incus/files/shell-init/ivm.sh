# ivm() shell wrapper (ansible-managed by roles/vm_incus). SOURCED into interactive
# zsh AND bash from `~/.local/share/ansible-managed/*/shell-init/*` (see the shell-init
# loops in roles/zsh/.zshrc.j2 and roles/bash/.bashrc.j2). Kept to the POSIX shell
# subset both shells share so ONE file serves both.
#
# `ivm` itself is a Python script on PATH. A child process cannot change its parent
# shell's directory, so `ivm cd <vm>` prints the VM's working-dir root and THIS wrapper
# runs `cd` in the interactive shell. Every OTHER subcommand is passed straight through
# to the real binary via `command ivm`, so the wrapper adds nothing but the `cd` case.
ivm() {
    if [ "$1" = cd ]; then
        # `command ivm` runs the real Python launcher (not this function): it prints the
        # dir on stdout for a named VM, or (bare `ivm cd`) lists managed VMs on stderr and
        # leaves stdout empty -> nothing to cd into.
        local _ivm_cd_target_dir
        _ivm_cd_target_dir="$(command ivm "$@")" || return
        if [ -n "$_ivm_cd_target_dir" ] && [ -d "$_ivm_cd_target_dir" ]; then
            builtin cd "$_ivm_cd_target_dir"
        elif [ -n "$_ivm_cd_target_dir" ]; then
            # Stdout was non-empty but not a directory (should not happen): surface it
            # rather than silently swallow it.
            printf '%s\n' "$_ivm_cd_target_dir"
        fi
    else
        command ivm "$@"
    fi
}
