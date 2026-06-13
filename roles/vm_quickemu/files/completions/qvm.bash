# qvm bash completion (ansible-managed by roles/vm_quickemu). bashrc sources
# every file under `~/.local/share/ansible-managed/*/bash-completions/` - see
# roles/dotfiles/.bashrc.j2. Two levels: subcommands, then their args -
# prebuilt OS names for `init`, snapshot actions, VM names for `--name`.

# qvm VM names = vms/<name>.conf stems under QVM_HOME (no daemon to ask - fast).
_qvm_vm_names() {
    local qvm_vms_dir="${QVM_HOME:-$HOME/.local/share/qvm}/vms"
    local conf_path
    for conf_path in "$qvm_vms_dir"/*.conf; do
        [[ -e "$conf_path" ]] || continue
        conf_path="${conf_path##*/}"
        printf '%s\n' "${conf_path%.conf}"
    done
}

_qvm() {
    COMPREPLY=()
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local subcommands="init start stop kill delete shell exec push pull snapshot info list"

    # --name takes a value: complete qvm VM names after it.
    if [[ "$prev" == "--name" ]]; then
        COMPREPLY=( $(compgen -W "$(_qvm_vm_names)" -- "$cur") )
        return
    fi

    # The subcommand is the first non-flag word after `qvm` (--name takes a value).
    local i sub=""
    for (( i = 1; i < COMP_CWORD; i++ )); do
        case "${COMP_WORDS[i]}" in
            --name) (( i++ )) ;;
            -*) ;;
            *) sub="${COMP_WORDS[i]}"; break ;;
        esac
    done

    if [[ -z "$sub" ]]; then
        COMPREPLY=( $(compgen -W "${subcommands} --name --dry-run" -- "$cur") )
        return
    fi

    case "$sub" in
        init)
            COMPREPLY=( $(compgen -W "tumbleweed debian fedora --disk-size --ram --cpus --yes" -- "$cur") )
            ;;
        start)
            COMPREPLY=( $(compgen -W "--gui" -- "$cur") )
            ;;
        delete)
            COMPREPLY=( $(compgen -W "--yes" -- "$cur") )
            ;;
        snapshot)
            # Only the action position is completed; the <tag> after it is free text.
            local snapshot_action="" word_index
            for (( word_index = i + 1; word_index < COMP_CWORD; word_index++ )); do
                [[ "${COMP_WORDS[word_index]}" == -* ]] && continue
                snapshot_action="${COMP_WORDS[word_index]}"; break
            done
            if [[ -z "$snapshot_action" ]]; then
                COMPREPLY=( $(compgen -W "apply create delete info" -- "$cur") )
            fi
            ;;
        push|pull)
            COMPREPLY=( $(compgen -A file -- "$cur") )
            ;;
    esac
}
complete -F _qvm qvm
