#!/usr/bin/env python3
# =============================================================================
# DEPRECATED - kept for in-flight migration only, do not use for new work.
# =============================================================================
# This validator existed to catch bare-x footguns in hand-edited deny rules.
# The new pipeline (scripts/gen_personal_dirs_aa_mixins.py) emits modes
# programmatically and validates the YAML input against a JSON Schema, so
# this bare-x check is no longer needed.
#
# Will be removed once every pathbased profile has migrated to the per-
# category includes (local_mixin_personal_dirs__for__<category>).
# =============================================================================

"""Print and validate local_mixin_deny_personal_dirs.

Prints the j2 template header followed by the rendered deny rules with line
numbers. Checks that every allow rule (no 'deny' keyword) uses a qualified
execute mode (ix, Px, px, Cx, cx, Ux, ux) instead of bare 'x'. Bare 'x' is
only valid inside a deny rule; in an allow rule it is a policy error.

Exits non-zero if any errors are found, so it can gate make targets.

Usage:
  python3 scripts/check_deny_personal_dirs.py
  python3 scripts/check_deny_personal_dirs.py roles/apparmor/local_vars/deny_personal_dirs.aa
"""

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DEFAULT_FILE = _ROOT / "roles" / "apparmor" / "local_vars" / "deny_personal_dirs.aa"
_TEMPLATE = _ROOT / "roles/apparmor/templates/local_mixin_deny_personal_dirs.aa.j2"

_SEP = "=" * 50

# ANSI color codes - only applied when stdout is a TTY.
_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

def _bold(s: str)     -> str: return _c("1",    s)
def _dim(s: str)      -> str: return _c("2",    s)
def _red(s: str)      -> str: return _c("31",   s)
def _yellow(s: str)   -> str: return _c("33",   s)
def _green(s: str)    -> str: return _c("32",   s)
def _cyan(s: str)     -> str: return _c("36",   s)
def _bold_red(s: str) -> str: return _c("1;31", s)

# Matches an AppArmor file rule line.
# A rule is: [audit] [deny] <path> <modes>,
# where path may be quoted or unquoted.
_RULE_RE = re.compile(
    r"^\s*"
    r"(?P<audit>audit\s+)?"
    r"(?P<deny>deny\s+)?"
    r"(?P<path>\"[^\"]+\"|[^\s]+)"
    r"\s+"
    r"(?P<modes>[a-zA-Z]+)"
    r"\s*,"
)

# x must be preceded by one of these qualifiers in an allow rule.
# Bare x (preceded by anything else, e.g. l, k, w) is invalid in allow rules.
_QUALIFIER_RE = re.compile(r"(?<![ipPcCuU])x")


def _has_bare_x(modes: str) -> bool:
    return bool(_QUALIFIER_RE.search(modes))


def _highlight_wildcards(s: str, color_fn) -> str:
    parts = s.split("*")
    return _yellow("*").join(color_fn(p) for p in parts)


def _colorize_rule(m: re.Match, raw: str, is_deny: bool) -> str:
    audit_s = m.group("audit") or ""
    deny_s  = m.group("deny")  or ""
    lead    = raw[:m.start("path") - len(audit_s) - len(deny_s)]
    path_s  = m.group("path")
    between = raw[m.end("path"):m.start("modes")]
    modes_s = m.group("modes")
    tail    = raw[m.end("modes"):]  # the ","

    kw        = _bold_red(audit_s + deny_s) if (audit_s or deny_s) else ""
    path_col  = _highlight_wildcards(path_s, _red if is_deny else _green)
    modes_col = _cyan(modes_s)
    return f"{lead}{kw}{path_col}{between}{modes_col}{tail}"


def _template_info(template: Path) -> tuple[list[tuple[int, str]], int]:
    """Return (numbered non-Jinja lines, line number where {{ lookup }} sits)."""
    if not template.exists():
        return [], 1
    lines = template.read_text(encoding="utf-8").splitlines()
    visible = [(i + 1, l) for i, l in enumerate(lines) if "{{" not in l]
    lookup_lineno = next((i + 1 for i, l in enumerate(lines) if "{{" in l), len(lines) + 1)
    return visible, lookup_lineno


def _check_file(filepath: Path) -> int:
    """Print and validate the file. Return the number of errors found."""
    if not filepath.exists():
        print(f"error: file not found: {filepath}", file=sys.stderr)
        return 1

    aa_lines = filepath.read_text(encoding="utf-8").splitlines()
    header_lines, aa_start = _template_info(_TEMPLATE)
    errors: list[tuple[int, str]] = []
    sep = _dim(" | ")

    total = aa_start - 1 + len(aa_lines)
    width = len(str(total))

    all_lines = header_lines + list(enumerate(aa_lines, aa_start))

    print(_bold(_SEP))
    print(_bold("local_mixin_deny_personal_dirs (rendered)"))
    print(_bold(_SEP))
    for lineno, raw in all_lines:
        lno = f"{lineno:{width}}"
        m = _RULE_RE.match(raw)
        if m is None or lineno < aa_start:
            print(f"{_dim(lno)}{sep}{_dim(raw)}")
            continue

        is_deny = m.group("deny") is not None
        modes = m.group("modes")

        if not is_deny and _has_bare_x(modes):
            annotation = _bold_red("  # ERROR: bare 'x' in allow rule - use ix / Px / Cx / Ux")
            print(f"{_dim(lno)}{sep}{_red(raw.rstrip())}{annotation}")
            errors.append((lineno, raw.rstrip()))
        else:
            print(f"{_dim(lno)}{sep}{_colorize_rule(m, raw, is_deny)}")

    print()
    print(_bold(_SEP))
    print("To regenerate: python3 scripts/gen_deny_personal_dirs.py <dir> [<dir> ...]")
    print("Example:       python3 scripts/gen_deny_personal_dirs.py ~/secret_projects ~/vault/*")
    print(_bold(_SEP))

    if errors:
        print(f"\n{_bold_red(f'Found {len(errors)} error(s):')}")
        for lineno, raw in errors:
            print(f"  line {lineno}: {raw.strip()}")
        print()
        print(
            "Hint: when removing 'deny' from a rule, replace bare 'x' in the mode\n"
            "string with a qualified execute mode:\n"
            "  ix      inherit: child runs under the same profile as parent (no env scrub)\n"
            "  px      named profile transition, env vars NOT scrubbed\n"
            "  Px      named profile transition, env vars scrubbed (safer)\n"
            "  cx      child profile transition (defined in same file), env NOT scrubbed\n"
            "  Cx      child profile transition, env scrubbed (safer)\n"
            "  ux      unconfined exec, env NOT scrubbed (avoid)\n"
            "  Ux      unconfined exec, env scrubbed (still unconfined - avoid)\n"
            "  pix/Pix px/Px with fallback to ix if no matching profile exists\n"
            "  cix/Cix cx/Cx with fallback to ix if no matching profile exists\n"
            "Uppercase P/C/U scrub the environment before exec; lowercase do not."
        )
        return len(errors)

    print(f"\n{_green('OK - no issues found.')}")
    return 0


def main() -> None:
    filepath = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_FILE
    sys.exit(_check_file(filepath))


if __name__ == "__main__":
    main()
