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

# Provisionable unit names for `provision`: distro package groups + thirdparty software
# (shared cache JSON) + dotfiles features. Names only (bash shows no descriptions). Same
# dynamic pattern as ivm's _ivm_unit_names.
_pvm_unit_names() {
    local shared_root="${SHARED_PREBUILT_PROVISION_ASSETS_ROOT:-$HOME/.local/share/ansible-managed/shared-prebuilt-provision-assets}"
    python3 - "$shared_root" 2>/dev/null <<'PY'
import json, os, sys
shared_root = sys.argv[1]
names = []
for f in ("distro-package-groups.json", "thirdparty-software.json"):
    p = os.path.join(shared_root, f)
    if os.path.exists(p):
        try:
            names += list(json.load(open(p)))
        except Exception:
            pass
dotfiles = os.path.join(shared_root, "dotfiles")
if os.path.isdir(dotfiles):
    names += sorted(os.listdir(dotfiles))
print("\n".join(dict.fromkeys(names)))
PY
}

_pvm() {
    COMPREPLY=()
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local subcommands="init build run env start stop rmc rmi rma reboot delete info update push resize provision shell sh shell-user sh-user shell-root sh-root zsh-user zsh-root bash-user bash-root agent top list help"

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
        top)
            COMPREPLY=( $(compgen -W "$(_pvm_container_names)" -- "$cur") )
            ;;
        resize)
            COMPREPLY=( $(compgen -W "--cpu --memory" -- "$cur") )
            ;;
        provision)
            COMPREPLY=( $(compgen -W "$(_pvm_unit_names)" -- "$cur") )
            ;;
    esac
}
complete -F _pvm pvm
