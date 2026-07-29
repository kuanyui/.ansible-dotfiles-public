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

# Installable `provision` unit names: distro-bundle + thirdparty-recipe registry keys +
# dotfiles feature dirs, from the SHARED provision-asset cache (read dynamically from
# the JSON, so it auto-tracks the registry). bash shows names only - no descriptions.
_qvm_unit_names() {
    local qvm_shared_assets_root="${SHARED_PREBUILT_PROVISION_ASSETS_ROOT:-$HOME/.local/share/ansible-managed/shared-prebuilt-provision-assets}"
    python3 - "$qvm_shared_assets_root" 2>/dev/null <<'PY'
import json, os, sys
shared_root = sys.argv[1]
LAUNCHER = "qvm"
def offered(entry):
    # Same `available_on` rule as the launcher's registry loader: the entry's list of
    # consumers; absent = every consumer.
    if not isinstance(entry, dict):
        return True
    available_on = entry.get("available_on")
    return available_on is None or LAUNCHER in available_on
seen = []
def add(name):
    if name not in seen:
        seen.append(name)
for f in ("distro-package-groups.json", "thirdparty-software.json"):
    p = os.path.join(shared_root, f)
    if os.path.exists(p):
        try:
            for key, val in json.load(open(p)).items():
                if offered(val):
                    add(key)
        except Exception:
            pass
dotfiles = os.path.join(shared_root, "dotfiles")
if os.path.isdir(dotfiles):
    for d in sorted(os.listdir(dotfiles)):
        add(d)
print("\n".join(seen))
PY
}

_qvm() {
    COMPREPLY=()
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    local subcommands="init start stop kill delete shell exec push pull snapshot provision info list"

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
        COMPREPLY=( $(compgen -W "${subcommands} --name --dry-run --shared-assets-root" -- "$cur") )
        return
    fi

    case "$sub" in
        init)
            COMPREPLY=( $(compgen -W "tumbleweed debian fedora --disk-size --ram --cpus --yes --provision" -- "$cur") )
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
        provision)
            # Unit names (bash shows names only; zsh adds descriptions).
            COMPREPLY=( $(compgen -W "$(_qvm_unit_names)" -- "$cur") )
            ;;
        push|pull)
            COMPREPLY=( $(compgen -A file -- "$cur") )
            ;;
    esac
}
complete -F _qvm qvm
