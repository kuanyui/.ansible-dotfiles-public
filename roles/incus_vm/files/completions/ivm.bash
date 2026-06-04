# ivm bash completion (ansible-managed by roles/incus_vm). bashrc sources every
# file under `~/.local/share/ansible-managed/*/bash-completions/` - see
# roles/dotfiles/.bashrc.j2. Two levels: subcommands, then template names for
# `init` / `env`.
_ivm() {
    COMPREPLY=()
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local subcommands="init shell shell-user shell-root start stop delete env overwrite-dotfiles update set-root-password unset-root-password snapshot gui"
    local templates_root="${IVM_ROOT:-$HOME/.local/share/ansible-managed/incus-vm}/vm-templates"

    # The subcommand is the first non-flag word after `ivm` (--root takes a value).
    local i sub=""
    for (( i = 1; i < COMP_CWORD; i++ )); do
        case "${COMP_WORDS[i]}" in
            --root) (( i++ )) ;;
            -*) ;;
            *) sub="${COMP_WORDS[i]}"; break ;;
        esac
    done

    if [[ -z "$sub" ]]; then
        COMPREPLY=( $(compgen -W "${subcommands} --root --dry-run --yes" -- "$cur") )
        return
    fi

    case "$sub" in
        init|env)
            local templates=""
            if [[ -d "$templates_root" ]]; then
                local template_file
                for template_file in "$templates_root"/*.yaml; do
                    [[ -e "$template_file" ]] || continue
                    template_file="${template_file##*/}"
                    templates+="${template_file%.yaml} "
                done
            fi
            COMPREPLY=( $(compgen -W "${templates}" -- "$cur") )
            ;;
    esac
}
complete -F _ivm ivm
