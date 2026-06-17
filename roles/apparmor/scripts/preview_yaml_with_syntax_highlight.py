"""ANSI syntax highlighting for the customized_extra_dirs.yml preview.

Used by gen_customized_extra_dirs_aa_mixins.py --validate-only (which
sandbox-apparmor and apply-apparmor both feed through). Token types:

  blue         path values        (after `path:` on each entry)
  green        category names     (inside `allow: [...]`)
  bold yellow  the `*` sentinel   ("every category" - rendered specially so
                                   it stands out from named categories)
  gray         comments           (both full-line `# ...` and trailing
                                   `  # ...` after a value)

Anything else (yaml keys, dashes, brackets, quotes) keeps the default
terminal color. Pure-Python, no external deps.

The patterns are tailored to customized_extra_dirs.yml's schema (path + allow);
this is not a general-purpose YAML highlighter.
"""

from __future__ import annotations

import os
import re
import sys

# ANSI escape codes.
_ANSI_RESET = "\x1b[0m"
_ANSI_PATH = "\x1b[34m"
_ANSI_CATEGORY = "\x1b[32m"
_ANSI_STAR = "\x1b[1;33m"
_ANSI_COMMENT = "\x1b[90m"

_DEFAULT_STAR_SENTINEL = "*"

_PATH_LINE_RE = re.compile(r"^(\s*-\s+path:\s*)(.+?)(\s*)$")
_INLINE_ALLOW_RE = re.compile(r"^(\s*allow:\s*)\[(.*?)\](\s*)$")
# Defensive fallback for the multi-line allow form (`allow:` then indented
# `- item` lines). Reached only if `_PATH_LINE_RE` did NOT match, so a
# top-level `- path:` entry is never mis-colored as a category.
_LIST_ITEM_RE = re.compile(r"^(\s+-\s+)(.+?)(\s*)$")
# Trailing `  # ...` after a value. Requires `\s+` before `#` so we never
# split a bare `#` that's part of a token (e.g. an unlikely path containing
# `#`). Quoted strings containing ` # ` would be mis-split, but customized_extra_dirs
# entries don't carry such paths in practice.
_INLINE_COMMENT_RE = re.compile(r"^(.+?)(\s+#.*)$")


def _color_allow_token(raw: str, star_sentinel: str) -> str:
    """Color one allow-list token. The star sentinel (default `*`) gets the
    star color; everything else is treated as a category name."""
    stripped = raw.strip().strip('"').strip("'")
    color = _ANSI_STAR if stripped == star_sentinel else _ANSI_CATEGORY
    return f"{color}{raw}{_ANSI_RESET}"


def _colorize_line(line: str, star_sentinel: str) -> str:
    # Full-line comment (`# ...` with optional leading whitespace).
    if line.lstrip().startswith("#"):
        return f"{_ANSI_COMMENT}{line}{_ANSI_RESET}"
    # Trailing inline comment: peel it off, recurse on the code half.
    m = _INLINE_COMMENT_RE.match(line)
    if m:
        code = _colorize_line(m.group(1), star_sentinel)
        return f"{code}{_ANSI_COMMENT}{m.group(2)}{_ANSI_RESET}"
    m = _PATH_LINE_RE.match(line)
    if m:
        return f"{m.group(1)}{_ANSI_PATH}{m.group(2)}{_ANSI_RESET}{m.group(3)}"
    m = _INLINE_ALLOW_RE.match(line)
    if m:
        prefix, items_str, suffix = m.group(1), m.group(2), m.group(3)
        if not items_str.strip():
            return line
        colored: list[str] = []
        for raw in items_str.split(","):
            stripped = raw.strip()
            if not stripped:
                colored.append(raw)
                continue
            leading = " " * (len(raw) - len(raw.lstrip()))
            trailing = " " * (len(raw) - len(raw.rstrip()))
            colored.append(f"{leading}{_color_allow_token(stripped, star_sentinel)}{trailing}")
        return f"{prefix}[{','.join(colored)}]{suffix}"
    m = _LIST_ITEM_RE.match(line)
    if m:
        return f"{m.group(1)}{_color_allow_token(m.group(2), star_sentinel)}{m.group(3)}"
    return line


def resolve_color_mode(mode: str) -> bool:
    """Resolve `--color={auto,always,never}` honoring the NO_COLOR env var."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def colorize_preview(
    text: str,
    color: bool,
    star_sentinel: str = _DEFAULT_STAR_SENTINEL,
) -> str:
    """Apply ANSI coloring to customized_extra_dirs.yml preview text. No-op when
    `color` is False. `star_sentinel` is the value treated as "all
    categories" (default `*`)."""
    if not color:
        return text
    return "\n".join(_colorize_line(ln, star_sentinel) for ln in text.splitlines())
