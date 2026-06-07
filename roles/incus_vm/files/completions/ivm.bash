# ivm bash completion (ansible-managed by roles/incus_vm). bashrc sources every
# file under `~/.local/share/ansible-managed/*/bash-completions/` - see
# roles/dotfiles/.bashrc.j2. Two levels: subcommands, then their args - template
# names for `init`/`env`, unit names for `provision`, `snapshot` actions + snapshot
# names, `user`/`root`.
# All installable unit names for `provision`: keys of the materialized distro-bundle
# + thirdparty-recipe registries (python3 is an ivm dependency, so always present).
_ivm_unit_names() {
    local root="${IVM_ROOT:-$HOME/.local/share/ansible-managed/incus-vm/ivm}"
    python3 - "$root" 2>/dev/null <<'PY'
import json, os, sys
root = sys.argv[1]
for f in ("distro-package-groups.json", "thirdparty-software.json"):
    p = os.path.join(root, f)
    if os.path.exists(p):
        try:
            print("\n".join(json.load(open(p))))
        except Exception:
            pass
PY
}

_ivm() {
    COMPREPLY=()
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local subcommands="init shell shell-user shell-root start reboot stop delete env list info overwrite-dotfiles update provision set-password unset-password enable-user-sudo disable-user-sudo snapshot gui"
    local templates_root="${IVM_ROOT:-$HOME/.local/share/ansible-managed/incus-vm/ivm}/templates"

    # --name / --root take a value: complete VM names after --name.
    if [[ "$prev" == "--name" ]]; then
        COMPREPLY=( $(compgen -W "$(incus list --format csv --columns n 2>/dev/null)" -- "$cur") )
        return
    fi

    # The subcommand is the first non-flag word after `ivm` (--root/--name take a value).
    local i sub=""
    for (( i = 1; i < COMP_CWORD; i++ )); do
        case "${COMP_WORDS[i]}" in
            --root|--name) (( i++ )) ;;
            -*) ;;
            *) sub="${COMP_WORDS[i]}"; break ;;
        esac
    done

    if [[ -z "$sub" ]]; then
        COMPREPLY=( $(compgen -W "${subcommands} --root --name --dry-run --yes" -- "$cur") )
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
        set-password|unset-password)
            COMPREPLY=( $(compgen -W "user root" -- "$cur") )
            ;;
        provision)
            COMPREPLY=( $(compgen -W "$(_ivm_unit_names)" -- "$cur") )
            ;;
        snapshot)
            # After `snapshot`: an action, then (for restore/delete/rename/show) an
            # EXISTING snapshot name. `i` indexes the `snapshot` word; flags may sit
            # between, so skip them. Mirrors `ivm snapshot <action> [snapname]`.
            local snapshot_action="" snapshot_action_index=-1 word_index
            for (( word_index = i + 1; word_index < COMP_CWORD; word_index++ )); do
                [[ "${COMP_WORDS[word_index]}" == -* ]] && continue
                snapshot_action="${COMP_WORDS[word_index]}"
                snapshot_action_index=$word_index
                break
            done
            if [[ -z "$snapshot_action" ]]; then
                COMPREPLY=( $(compgen -W "create list restore delete rename show" -- "$cur") )
            else
                # Count non-flag positional args already given after the action: only
                # the FIRST one is an existing snapshot name (rename's 2nd arg is new).
                local snapshot_positional=0
                for (( word_index = snapshot_action_index + 1; word_index < COMP_CWORD; word_index++ )); do
                    [[ "${COMP_WORDS[word_index]}" == -* ]] || (( snapshot_positional++ ))
                done
                case "$snapshot_action" in
                    restore|delete|rename|show)
                        if (( snapshot_positional == 0 )); then
                            # Target VM: --name wins, else the VM bound to $PWD via the
                            # user.ivm_init_at_dir tag (exact-cwd match, no ancestor walk).
                            local snapshot_vm="" name_index
                            for (( name_index = 1; name_index < COMP_CWORD; name_index++ )); do
                                if [[ "${COMP_WORDS[name_index]}" == "--name" ]]; then
                                    snapshot_vm="${COMP_WORDS[name_index+1]}"
                                    break
                                fi
                            done
                            [[ -z "$snapshot_vm" ]] && snapshot_vm="$(incus list --format csv --columns n "user.ivm_init_at_dir=$PWD" 2>/dev/null)"
                            [[ -n "$snapshot_vm" ]] && COMPREPLY=( $(compgen -W "$(incus snapshot list "$snapshot_vm" --format csv --columns n 2>/dev/null)" -- "$cur") )
                        fi
                        ;;
                esac
            fi
            ;;
    esac
}
complete -F _ivm ivm
