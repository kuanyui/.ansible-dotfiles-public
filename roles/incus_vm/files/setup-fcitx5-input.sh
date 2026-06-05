#!/bin/sh
# Idempotent, SURGICAL fcitx5 input-method setup. Run as the TARGET USER on the
# host or inside an ivm guest. Touches ONLY the keys below; every other key in
# every file is left exactly as-is (and missing keys fall back to fcitx5's
# defaults), so this is safe to re-run and robust across fcitx5 versions/distros.
# mozc's own settings (incl. candidate-selection shortcut) live in a binary
# protobuf and are deliberately NOT touched.
#
# After running on a host where fcitx5 is already live, reload it: `fcitx5 -r`.
set -eu

conf_dir="${XDG_CONFIG_HOME:-$HOME/.config}/fcitx5"
mkdir -p "$conf_dir/conf"

# set_conf_key FILE KEY VALUE - set KEY=VALUE, replacing the existing line in
# place (every other line preserved) or appending it if absent. Idempotent.
set_conf_key() {
    _file=$1; _key=$2; _value=$3
    if [ -f "$_file" ] && grep -q "^${_key}=" "$_file"; then
        sed -i "s|^${_key}=.*|${_key}=${_value}|" "$_file"
    else
        printf '%s=%s\n' "$_key" "$_value" >> "$_file"
    fi
}

# chewing: only these three keys (selection keys / page size / space-selects).
chewing_conf="$conf_dir/conf/chewing.conf"
set_conf_key "$chewing_conf" SelectionKey 'asdfghjkl;'
set_conf_key "$chewing_conf" PageSize 10
set_conf_key "$chewing_conf" SpaceAsSelection True

# Enabled input methods (keyboard-us + mozc + chewing). The profile is a
# structured multi-section file, not independent keys, so we don't sed it; we
# write it ONLY when those IMs aren't already enabled (a fresh guest) and leave
# an already-configured profile (your host) untouched.
profile="$conf_dir/profile"
if ! { [ -f "$profile" ] && grep -q '^Name=mozc$' "$profile" && grep -q '^Name=chewing$' "$profile"; }; then
    cat > "$profile" <<'EOF'
[Groups/0]
Name=Default
Default Layout=us
DefaultIM=keyboard-us

[Groups/0/Items/0]
Name=keyboard-us
Layout=

[Groups/0/Items/1]
Name=mozc
Layout=

[Groups/0/Items/2]
Name=chewing
Layout=

[GroupOrder]
0=Default
EOF
fi
