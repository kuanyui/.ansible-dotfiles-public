#!/usr/bin/env bash
# Temporary PR1 validation: render j2 templates and diff against the
# hand-written claude/ and codex/ trees still present in this repo.
#
# A clean PR1 means every remaining diff is one of the documented
# "intentional convergence" items listed below. Anything else is a bug.
#
# Drop this script once PR2 moves rendered output out of the repo.

set -uo pipefail

cd "$(dirname "$0")"

echo "=== Running render_j2.py ==="
python3 render_j2.py || exit 1
echo

# README.md and assets/selinux/ are non-templated static assets that
# render_j2.py does not produce. Excluded from diff.
DIFF_EXCLUDES=(--exclude=README.md --exclude=selinux)

CONTAINERS=(claude codex)
EXIT=0

for name in "${CONTAINERS[@]}"; do
    echo "=============================================================="
    echo " ${name}: diff -r rendered/${name}/ ${name}/"
    echo "=============================================================="
    if diff -r --brief "${DIFF_EXCLUDES[@]}" "rendered/${name}/" "${name}/" >/dev/null 2>&1; then
        echo "  (byte-identical)"
    else
        diff -r "${DIFF_EXCLUDES[@]}" "rendered/${name}/" "${name}/"
        EXIT=1
    fi
    echo
done

echo "=============================================================="
echo " Expected (intentional convergence in PR1):"
echo "=============================================================="
cat <<'EOF'
  claude/Makefile                         no diff (canonical)
  claude/assets/Dockerfile                no diff
  claude/assets/dotfiles/user/.{zshrc,bashrc}
                                          no diff
  claude/assets/dotfiles/root/.zshrc
                                          drops 1 stray blank line at line 60
                                          (drift; user/.zshrc has no such gap)

  codex/Makefile                          gains HIDE_GIT_DIR / HIDE_VSCODE_DIR
                                          gains AppArmor section
                                          gains SELinux targets
                                          gains c-env line for HIDE_GIT_DIR
                                          gains $(_CONTAINER_RUN_HIDE_DIRS_ARGS) in c-run
                                          drops unused REQUIRE_DIR macro
                                          typo: "You've" -> "You have"
                                          comment whitespace: "# 	$(" -> "#	$("
                                          trailing newline normalized
  codex/assets/Dockerfile                 no diff
  codex/assets/dotfiles/user/.bashrc      1-blank-line drift fix (line 14)
  codex/assets/dotfiles/user/.zshrc       no diff
  codex/assets/dotfiles/root/.bashrc      1-blank-line drift fix (line 12)
  codex/assets/dotfiles/root/.zshrc       drops 1 stray blank line at line 60
EOF

if [ "$EXIT" -eq 0 ]; then
    echo
    echo "RESULT: all byte-identical."
else
    echo
    echo "RESULT: differences above. Verify each one is in the expected list."
fi

exit "$EXIT"
