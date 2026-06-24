# pvm bash completion (ansible-managed by roles/vm_podman). bashrc sources every
# file under `~/.local/share/ansible-managed/*/bash-completions/` - see
# roles/bash/.bashrc.j2. Two levels: subcommands, then their args - template names
# for init/build/run/env, container names for --name, runtime values for --runtime.

# Template names = *.yaml stems under the templates dir (shipped + user).
_pvm_template_names() {
    local pvm_templates_dir="${PVM_HOME:-$HOME/.local/share/ansible-managed/vm-podman/pvm}/templates"
    local template_path
    for template_path in "$pvm_templates_dir"/*.yaml; do
        [[ -e "$template_path" ]] || continue
        template_path="${template_path##*/}"
        printf '%s\n' "${template_path%.yaml}"
    done
}

# pvm-managed container names (ask podman; empty if podman is absent).
_pvm_container_names() {
    podman ps --all --filter 'name=^pvm-' --format '{{.Names}}' 2>/dev/null
}

_pvm() {
    COMPREPLY=()
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local subcommands="init build run env start stop rmc rmi rma reboot delete info update push shell sh shell-user sh-user shell-root sh-root zsh-user zsh-root bash-user bash-root agent list help"

    # Flags that take a value: complete that value, not a subcommand.
    if [[ "$prev" == "--name" ]]; then
        COMPREPLY=( $(compgen -W "$(_pvm_container_names)" -- "$cur") )
        return
    fi
    if [[ "$prev" == "--runtime" ]]; then
        COMPREPLY=( $(compgen -W "crun libkrun" -- "$cur") )
        return
    fi

    # The subcommand is the first non-flag word (--name / --runtime take a value).
    local i sub=""
    for (( i = 1; i < COMP_CWORD; i++ )); do
        case "${COMP_WORDS[i]}" in
            --name|--runtime) (( i++ )) ;;
            -*) ;;
            *) sub="${COMP_WORDS[i]}"; break ;;
        esac
    done

    if [[ -z "$sub" ]]; then
        COMPREPLY=( $(compgen -W "${subcommands} --name --dry-run --runtime --shared-assets-root" -- "$cur") )
        return
    fi

    case "$sub" in
        init)
            COMPREPLY=( $(compgen -W "$(_pvm_template_names) --rebuild --yes" -- "$cur") )
            ;;
        build)
            COMPREPLY=( $(compgen -W "$(_pvm_template_names) --rebuild" -- "$cur") )
            ;;
        run|env)
            COMPREPLY=( $(compgen -W "$(_pvm_template_names)" -- "$cur") )
            ;;
        reboot|delete)
            COMPREPLY=( $(compgen -W "--yes" -- "$cur") )
            ;;
        push)
            COMPREPLY=( $(compgen -f -- "$cur") $(compgen -W "--as-root" -- "$cur") )
            ;;
    esac
}
complete -F _pvm pvm
