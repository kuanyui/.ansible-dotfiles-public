#!/bin/bash
# Run the Ansible playbook in a throwaway rootless Podman container, produce
# a before/after unified diff of all deployed files, then syntax-validate
# every deployed AppArmor profile with apparmor_parser --skip-kernel-load.
#
# What can and cannot be tested here:
#   CAN:  file contents, permissions, template rendering, syntax validation
#   CANNOT: kernel profile loading (needs CAP_MAC_ADMIN), systemd services
#
# Usage: ./scripts/sandbox_diff.sh [IMAGE]
# Default: debian:bookworm
# Requirements: rootless podman

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE="${1:-debian:bookworm}"
CONTAINER="ansible-sandbox-$$"
SANDBOX_USER="sandboxuser"
SNAP_BEFORE="/tmp/ansible-sandbox-before-$$.tar.gz"
SNAP_AFTER="/tmp/ansible-sandbox-after-$$.tar.gz"
DIFF_BEFORE="/tmp/ansible-sandbox-diffbefore-$$"
DIFF_AFTER="/tmp/ansible-sandbox-diffafter-$$"
PLAYBOOK_RC=0
SYNTAX_RC=0
IDEMPOTENCE_RC=0

# Absolute paths inside the container to snapshot (before and after the playbook).
SNAP_ABS_PATHS="/etc/apparmor.d /home/$SANDBOX_USER/.local /usr/local/share/applications"

cleanup() {
    echo ""
    echo "--- cleaning up ---"
    podman rm -f "$CONTAINER" 2>/dev/null || true
    rm -f "$SNAP_BEFORE" "$SNAP_AFTER"
    rm -rf "$DIFF_BEFORE" "$DIFF_AFTER"
}
trap cleanup EXIT INT TERM

# =============================================
# Pre-flight check
# =============================================

if ! command -v podman &>/dev/null; then
    printf 'ERROR: podman not found.\n  Install: sudo apt install podman\n' >&2
    exit 1
fi

if [ ! -f "$PROJECT_DIR/roles/apparmor/local_vars/deny_personal_dirs.aa" ]; then
    printf 'ERROR: roles/apparmor/local_vars/deny_personal_dirs.aa not found.\n  Run: python3 scripts/gen_deny_personal_dirs.py <path> [<path>...]\n' >&2
    exit 1
fi

# =============================================
# Container setup
# =============================================

echo "==> Starting container ($IMAGE)..."
podman run -d --name "$CONTAINER" "$IMAGE" sleep infinity

echo "==> Installing prerequisites..."
podman exec "$CONTAINER" apt-get update -qq
# apparmor: provides apparmor_parser binary and system abstractions/tunables
# needed for real profile syntax validation (--skip-kernel-load is pure userspace, no kernel).
podman exec "$CONTAINER" apt-get install -y --no-install-recommends \
    python3 ansible-core sudo apparmor 2>&1 \
    | grep -E "^(Get:|Inst |Setting up)" || true

echo "==> Creating sandbox user '$SANDBOX_USER' with passwordless sudo..."
podman exec "$CONTAINER" useradd -m -s /bin/bash "$SANDBOX_USER"
podman exec "$CONTAINER" bash -c \
    "echo '$SANDBOX_USER ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/$SANDBOX_USER \
     && chmod 440 /etc/sudoers.d/$SANDBOX_USER"

echo "==> Copying Firefox profiles.ini from host..."
# The real profiles.ini produces accurate per-profile AppArmor rules.
# If it does not exist (Firefox not installed), we do not create it - the
# playbook will abort at the firefox task exactly as it would on this machine.
FIREFOX_PROFILES_INI="$HOME/.mozilla/firefox/profiles.ini"
if [ -f "$FIREFOX_PROFILES_INI" ]; then
    podman exec "$CONTAINER" mkdir -p "/home/$SANDBOX_USER/.mozilla/firefox"
    podman cp "$FIREFOX_PROFILES_INI" "$CONTAINER:/home/$SANDBOX_USER/.mozilla/firefox/profiles.ini"
    podman exec "$CONTAINER" chown -R "$SANDBOX_USER:$SANDBOX_USER" "/home/$SANDBOX_USER/.mozilla"
else
    echo "  $FIREFOX_PROFILES_INI not found - firefox tasks will be skipped by the playbook"
fi

echo "==> Installing dummy commands..."
for cmd in apparmor_parser systemctl aa-enforce aa-status aa-disable aa-complain; do
    podman cp "$SCRIPT_DIR/sandbox_dummy_commands/$cmd" "$CONTAINER:/usr/local/bin/$cmd"
done
podman exec "$CONTAINER" chmod +x \
    /usr/local/bin/apparmor_parser \
    /usr/local/bin/systemctl \
    /usr/local/bin/aa-enforce \
    /usr/local/bin/aa-status \
    /usr/local/bin/aa-disable \
    /usr/local/bin/aa-complain

echo "==> Preparing OS-baseline directories..."
# Only create what the apparmor package provides on a real Debian install.
# Every other directory (_backup_of_default_profiles_from_package_manager,
# /usr/local/share/applications, ~/.local/bin, ~/.local/share/applications, ...)
# is created by the playbook itself - must NOT be pre-created here.
podman exec "$CONTAINER" bash -c "mkdir -p /etc/apparmor.d/abstractions"

echo "==> Copying project into container..."
podman exec "$CONTAINER" mkdir -p /playbook
podman cp "$PROJECT_DIR/." "$CONTAINER:/playbook"
podman exec "$CONTAINER" chown -R "$SANDBOX_USER:$SANDBOX_USER" /playbook

# =============================================
# Before snapshot
# =============================================

echo "==> Snapshotting before state..."
# tar exits non-zero if any listed path does not exist; suppress with '|| true'.
podman exec "$CONTAINER" bash -c \
    "tar -czf /tmp/snap.tar.gz $SNAP_ABS_PATHS 2>/dev/null || true"
podman cp "$CONTAINER:/tmp/snap.tar.gz" "$SNAP_BEFORE"

# =============================================
# Run playbook
# =============================================

echo ""
echo "==> Running playbook as '$SANDBOX_USER' (full output follows)..."
echo "------------------------------------------------------------"
podman exec --user "$SANDBOX_USER" "$CONTAINER" \
    bash -c "cd /playbook && ansible-playbook -i localhost, -c local playbooks/site.yml" \
    || PLAYBOOK_RC=$?
echo "------------------------------------------------------------"

# =============================================
# After snapshot
# =============================================

echo ""
echo "==> Snapshotting after state..."
podman exec "$CONTAINER" bash -c \
    "tar -czf /tmp/snap.tar.gz $SNAP_ABS_PATHS 2>/dev/null || true"
podman cp "$CONTAINER:/tmp/snap.tar.gz" "$SNAP_AFTER"

# =============================================
# Unified diff
# =============================================

mkdir -p "$DIFF_BEFORE" "$DIFF_AFTER"
tar --no-same-owner -xzf "$SNAP_BEFORE" -C "$DIFF_BEFORE" 2>/dev/null || true
tar --no-same-owner -xzf "$SNAP_AFTER"  -C "$DIFF_AFTER"  2>/dev/null || true

echo ""
echo "============================================================"
echo " SANDBOX DIFF  (before -> after)"
echo "============================================================"
echo ""

# Strip the temp-dir prefix so paths read as a/etc/apparmor.d/...
DIFF_OUTPUT=$(diff -ruN "$DIFF_BEFORE/" "$DIFF_AFTER/" \
    | sed \
        -e "s|^--- ${DIFF_BEFORE}/|--- a/|" \
        -e "s|^+++ ${DIFF_AFTER}/|+++ b/|" \
    || true)

# Highlight diff via `git-delta` or fallback to `grep`
if command -v delta &>/dev/null; then
    printf '%s\n' "$DIFF_OUTPUT" | delta --paging=never
else
    printf '%s\n' "$DIFF_OUTPUT" | grep --color=always -E '^(\+.*|-.*)$|$'
fi
echo ""
echo "------------------------------------------------------------"
echo " CHANGED FILES"
echo "------------------------------------------------------------"
printf '%s\n' "$DIFF_OUTPUT" \
    | awk '
        /^--- a\// { sub(/^--- a\//, ""); sub(/\t.*$/, ""); print }
        /^\+\+\+ b\// { sub(/^\+\+\+ b\//, ""); sub(/\t.*$/, ""); print }
    ' \
    | grep -v '^/dev/null$' \
    | sort -u \
    | sed 's/^/  /'

# =============================================
# AppArmor profile syntax validation
# =============================================
# apparmor_parser --skip-kernel-load is pure userspace: validates syntax including all
# #include <abstractions/...> directives without touching the kernel.
# Abstractions deployed by the playbook are already in place at this point.

echo ""
echo "============================================================"
echo " APPARMOR SYNTAX CHECK"
echo "============================================================"
echo ""

podman exec "$CONTAINER" bash -c '
    errors=0
    total=0
    while IFS= read -r profile; do
        total=$((total + 1))
        name=$(basename "$profile")
        result=$(/usr/sbin/apparmor_parser --skip-kernel-load "$profile" 2>&1)
        if [ $? -eq 0 ]; then
            printf "  OK    %s\n" "$name"
        else
            printf "  FAIL  %s\n" "$name"
            printf "%s\n" "$result" | sed "s/^/        /"
            errors=$((errors + 1))
        fi
    done < <(find /etc/apparmor.d -maxdepth 1 -name "local_*" -type f 2>/dev/null | sort)
    echo ""
    printf "  %d/%d profiles passed.\n" "$((total - errors))" "$total"
    exit $errors
' || SYNTAX_RC=$?

# =============================================
# Idempotence check
# =============================================

# FIXME: This always failed.

echo ""
echo "============================================================"
echo " IDEMPOTENCE CHECK  (second run)"
echo "============================================================"
echo ""

IDEMPOTENCE_OUTPUT=$(podman exec --user "$SANDBOX_USER" "$CONTAINER" \
    bash -c "cd /playbook && ansible-playbook -i localhost, -c local playbooks/site.yml" 2>&1) \
    || IDEMPOTENCE_RC=$?

if [ "$IDEMPOTENCE_RC" -ne 0 ]; then
    echo "  FAIL - second run exited with code $IDEMPOTENCE_RC"
    printf '%s\n' "$IDEMPOTENCE_OUTPUT" | tail -20 | sed 's/^/  /'
elif printf '%s\n' "$IDEMPOTENCE_OUTPUT" | grep -qE 'changed=[^0]'; then
    echo "  FAIL - tasks still report changes on second run:"
    printf '%s\n' "$IDEMPOTENCE_OUTPUT" | grep -E 'changed=' | sed 's/^/  /'
    IDEMPOTENCE_RC=1
else
    echo "  OK"
fi

if [ "$PLAYBOOK_RC" -ne 0 ]; then
    echo ""
    echo "WARNING: first ansible-playbook run exited with code $PLAYBOOK_RC"
    echo "         The diff and syntax check above may be incomplete."
fi

exit $(( PLAYBOOK_RC != 0 || SYNTAX_RC != 0 || IDEMPOTENCE_RC != 0 ))
