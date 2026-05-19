#!/usr/bin/env python3
"""Generate an AppArmor deny-rule scaffold for personal directories.

Usage examples:
  python3 scripts/gen_deny_personal_dirs.py ~/secret_projects
  python3 scripts/gen_deny_personal_dirs.py ~/secret_projects ~/vault/*
  python3 scripts/gen_deny_personal_dirs.py ~/vault/* -o roles/apparmor/local_vars/my_deny.aa
"""

import argparse
import glob
import os
import sys
from pathlib import Path

_DEFAULT_OUTPUT = "roles/apparmor/local_vars/deny_personal_dirs.aa"


def resolve_paths(raw: str) -> list[Path]:
    """Expand ~ and glob in a path argument, return only existing directories."""
    expanded = os.path.expanduser(raw)
    matches = glob.glob(expanded)
    if not matches:
        return []
    return [Path(m) for m in matches if Path(m).is_dir()]


def build_rules(dirs: list[Path]) -> str:
    lines: list[str] = []
    for d in sorted(dirs):
        p = str(d).rstrip("/")
        if " " in p:
            lines.append(f'  audit deny "{p}/{{,**}}" mrwklx,')
        else:
            lines.append(f"  audit deny {p}/{{,**}} mrwklx,")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) == 1:
        print(__doc__)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description=(
            "Scaffold AppArmor audit-deny rules for personal directories. "
            "Edit the output file to remove unwanted entries, then run the playbook."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH_OR_GLOB",
        help=(
            "Directory path or shell glob. "
            "~ is expanded. "
            "Globs are resolved; only directories are kept. "
            "Example: ~/secrets ~/projects/*"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=_DEFAULT_OUTPUT,
        help=f"Output file (default: {_DEFAULT_OUTPUT}). Created if absent.",
    )
    args = parser.parse_args()

    resolved: list[Path] = []
    for raw in args.paths:
        found = resolve_paths(raw)
        if not found:
            print(f"error: no directories matched: {raw!r}", file=sys.stderr)
            sys.exit(1)
        resolved.extend(found)

    # Deduplicate while preserving sort order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in resolved:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    if not unique:
        print("error: no valid directories found - nothing written.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rules = build_rules(unique)
    output_path.write_text(rules + "\n", encoding="utf-8")

    n = len(unique)
    print(f"Created `audit deny` rules for {n} director{'y' if n == 1 else 'ies'}:")
    for p in unique:
        print(f"  {p}")
    print(f"\nOutput file:\n  {output_path.resolve()}")
    print("\n\nRemember to edit the file to remove unwanted entries, then run the playbook.")
    print("\n" + "=" * 50 + "\n")
    print(
        "Note: if you remove 'deny' from any rule to allow access, you must also\n"
        "replace the bare 'x' in the mode string with a qualified execute mode:\n\n"
        "  ix   - inherit parent profile (most common)\n"
        "  Px   - named profile transition, env scrubbed\n"
        "  px   - named profile transition, env NOT scrubbed\n"
        "  Cx   - child profile transition, env scrubbed\n"
        "  cx   - child profile transition, env NOT scrubbed\n"
        "  Ux   - unconfined, env scrubbed   (avoid)\n"
        "  ux   - unconfined, env NOT scrubbed  (avoid)\n\n"
        "Run scripts/check_deny_personal_dirs.py to verify."
    )


if __name__ == "__main__":
    main()
