#!/usr/bin/env python3
"""Build per-category AppArmor abstractions from customized_extra_dirs.yml.

Reads:
  roles/apparmor/app_categories.yml         (category list)
  roles/apparmor/local_vars/customized_extra_dirs.yml  (user-edited definitions)

Writes one file per category, plus a deny-all abstraction, to:
  roles/apparmor/local_vars/generated_abstractions/
      local_mixin_customized_extra_dirs__for__<category>
      local_mixin_customized_extra_dirs__DENY_ALL   (every listed dir denied, allow lists ignored)

The YAML is validated against a JSON Schema. The schema's `allow` enum is
populated from app_categories.yml at run time so the two stay in sync.

Each entry in customized_extra_dirs.yml looks like:
    - path: "/home/user/Music Sheets"
      allow: [pdf_viewer]            # only the pdf_viewer abstraction allows
    - path: "/home/user/Downloads"
      allow: ["*"]                   # every abstraction allows
    - path: "/home/user/secret"
      allow: []                      # no abstraction allows (deny everywhere)

For each category C, for each entry E:
    if "*" in E.allow OR C in E.allow:
        emit:  E.path/{,**} mrwklix,
    else:
        emit:  audit deny E.path/{,**} mrwklx,

Usage:
  python3 roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py
  python3 roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py --in PATH --out DIR
  python3 roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py --dump-schema
"""

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

# Sibling helper - kept in its own module because syntax highlighting is a
# preview-UX concern, not part of the abstraction-generation pipeline.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview_yaml_with_syntax_highlight import (  # noqa: E402
    colorize_preview,
    resolve_color_mode,
)
# `jsonschema` is intentionally NOT imported at module top. It is a hard runtime
# dep only of `validate_definitions()`. Importing it eagerly here would mean any
# transitive import (e.g. scaffold script -> this module for `build_schema` /
# `write_schema` helpers) crashes with ModuleNotFoundError on a fresh box
# before the role's `ansible.builtin.package` task has had a chance to install
# `python3-jsonschema`. Lazy import inside `validate_definitions()` instead.

# `roles/apparmor/scripts/<this file>` -> `roles/apparmor/` is two `parent`s up.
_ROLE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_CATEGORIES_FILE = _ROLE_DIR / "app_categories.yml"
_DEFAULT_DEFINITIONS_FILE = _ROLE_DIR / "local_vars" / "customized_extra_dirs.yml"
_DEFAULT_OUTPUT_DIR = _ROLE_DIR / "local_vars" / "generated_abstractions"

_ANY_SENTINEL = "*"

# Special abstraction (not a category): denies every listed directory regardless
# of its allow list. For profiles that must never touch any of them - e.g.
# container base profiles. Reads the SAME source as the per-category
# abstractions, so there is one source of truth (replaces the old,
# separately-sourced all-or-nothing deny mixin).
_DENY_ALL_ABSTRACTION_NAME = "local_mixin_customized_extra_dirs__DENY_ALL"

# AppArmor file modes:
#   allow rule uses `ix` (inherit-exec) because every other case we have
#   seen wants the child to run under the parent profile.
#   deny rule uses bare `x` because `audit deny ... x` is valid (deny mode
#   characters do not need a qualifier; the qualifier only applies to allow).
_ALLOW_MODES = "mrwklix"
_DENY_MODES = "mrwklx"


def load_categories(path: Path) -> list[dict[str, str]]:
    """Load and validate the categories list.

    Returns a list of `{name, description}` dicts in declared order. Both
    fields are required - description carries the hover/autocomplete text
    shown by IDEs via the generated JSON Schema."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "categories" not in data:
        raise ValueError(f"{path}: missing top-level `categories:` key")
    cats = data["categories"]
    if not isinstance(cats, list) or not cats:
        raise ValueError(f"{path}: `categories` must be a non-empty list")

    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for i, c in enumerate(cats):
        if not isinstance(c, dict):
            raise ValueError(
                f"{path}: categories[{i}] must be a mapping with `name` and "
                f"`description`, got {type(c).__name__}"
            )
        name = c.get("name")
        desc = c.get("description")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{path}: categories[{i}].name must be a non-empty string")
        if not isinstance(desc, str) or not desc.strip():
            raise ValueError(
                f"{path}: categories[{i!s}] (name={name!r}).description must be "
                f"a non-empty string"
            )
        extra = set(c.keys()) - {"name", "description"}
        if extra:
            raise ValueError(
                f"{path}: categories[{i}] (name={name!r}) has unexpected "
                f"keys: {sorted(extra)}"
            )
        if name == _ANY_SENTINEL:
            raise ValueError(
                f"{path}: {_ANY_SENTINEL!r} is a reserved sentinel and must "
                f"not appear as a category name"
            )
        if name in seen:
            raise ValueError(f"{path}: duplicate category name {name!r}")
        seen.add(name)
        out.append({"name": name, "description": desc})
    return out


def build_schema(categories: list[dict[str, str]]) -> dict[str, Any]:
    """Hand-written JSON Schema with the category list injected at run time.

    The per-category branch uses `oneOf` of `const`s rather than a flat
    `enum`, so each accepted value carries its own `description`. This is
    what Red Hat YAML extension / coc-yaml / lsp-mode show as hover text
    and autocomplete hints."""
    category_alternatives = [
        {"const": c["name"], "description": c["description"]}
        for c in categories
    ]
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "customized_extra_dirs definitions",
        "description": (
            "Per-path access policy consumed by "
            "roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py."
        ),
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "allow"],
            "properties": {
                "path": {
                    "type": "string",
                    # Absolute path, no trailing slash. The builder appends
                    # `/{,**}` itself so the entry must denote the directory,
                    # not the directory's contents.
                    "pattern": r"^/.+[^/]$",
                },
                "allow": {
                    "oneOf": [
                        {
                            "description": (
                                f"The {_ANY_SENTINEL!r} sentinel: every "
                                f"category abstraction allows this path. "
                                f"Must appear alone."
                            ),
                            "type": "array",
                            "items": {"const": _ANY_SENTINEL},
                            "minItems": 1,
                            "maxItems": 1,
                        },
                        {
                            "description": (
                                "Zero or more named categories. Empty list "
                                "means no abstraction allows (deny everywhere)."
                            ),
                            "type": "array",
                            "items": {"oneOf": category_alternatives},
                            "uniqueItems": True,
                        },
                    ]
                },
            },
        },
    }


def _ensure_jsonschema() -> None:
    """Probe for `jsonschema` and install `python3-jsonschema` via sudo if
    missing. Runs whenever this script is invoked in any mode that needs
    schema validation (default build, --validate-only, --confirm). The
    sandbox `_pre_flight` and `make apply-apparmor` both reach jsonschema
    through this single entry point - no duplicate install logic in the
    sandbox config or the role's tasks. Distro package name is the same
    on Debian / openSUSE / Fedora."""
    probe = subprocess.run(
        [sys.executable, "-c", "import jsonschema"],
        check=False,
        capture_output=True,
    )
    if probe.returncode == 0:
        return

    if shutil.which("zypper"):
        cmd = ["sudo", "zypper", "--non-interactive", "install", "python3-jsonschema"]
    elif shutil.which("apt-get"):
        cmd = ["sudo", "apt-get", "install", "--yes", "python3-jsonschema"]
    elif shutil.which("dnf"):
        cmd = ["sudo", "dnf", "install", "--assumeyes", "python3-jsonschema"]
    else:
        raise RuntimeError(
            "No supported package manager found (need zypper, apt-get, or dnf). "
            "Install python3-jsonschema manually and retry."
        )
    print(
        "==> python3-jsonschema is required by this script but is not installed.\n"
        "    Source: your distro's official package repository (NOT pip / PyPI).\n"
        "    About to run the following command; sudo may prompt for your password:\n"
        "\n"
        f"        {shlex.join(cmd)}\n"
        "\n"
        "    Press Ctrl+C now to abort, or wait for sudo to prompt.\n"
    )
    subprocess.run(cmd, check=True)


def _format_path_error(error_path: list[Any]) -> str:
    """Render a jsonschema error path like `[3].allow[1]` for readability."""
    if not error_path:
        return "(top level)"
    parts: list[str] = []
    for p in error_path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            if parts:
                parts.append(f".{p}")
            else:
                parts.append(str(p))
    return "".join(parts)


def validate_definitions(definitions: Any, schema: dict[str, Any]) -> None:
    """Validate definitions against the schema. Raise on any error.

    `jsonschema` is lazy-imported here so the module can be loaded (and its
    schema/path helpers reused) on hosts that have not yet installed the
    `python3-jsonschema` distro package."""
    from jsonschema import Draft7Validator  # noqa: PLC0415
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(definitions), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    msgs: list[str] = []
    for e in errors:
        where = _format_path_error(list(e.absolute_path))
        msgs.append(f"  {where}: {e.message}")
    raise ValueError(
        "customized_extra_dirs.yml failed schema validation:\n" + "\n".join(msgs)
    )


def _quote_path_if_needed(p: str) -> str:
    """Match the existing roles/apparmor convention: quote only when path
    contains whitespace. Other characters are left raw; if a user puts an
    AppArmor-special character (`{`, `*`, ...) in a real path, they need
    to handle it themselves."""
    if any(c.isspace() for c in p):
        return f'"{p}"'
    return p


def _rule_for_entry(path: str, allow: bool) -> str:
    """Render one AppArmor file rule for the given path."""
    quoted = _quote_path_if_needed(f"{path}/{{,**}}")
    if allow:
        return f"  {quoted} {_ALLOW_MODES},"
    return f"  audit deny {quoted} {_DENY_MODES},"


def render_abstraction(
    category: dict[str, str],
    definitions: list[dict[str, Any]],
) -> str:
    """Render the body of one abstraction file. The category's description
    is folded into the header comment so the abstraction self-documents."""
    name = category["name"]
    # Prefix every description line with `# ` so the AppArmor parser ignores it.
    desc_lines = "\n".join(f"# {ln}" if ln else "#" for ln in category["description"].rstrip().splitlines())
    header = (
        "# Managed by Ansible - do not edit manually\n"
        f"# Generated by roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py\n"
        f"# Category: {name}\n"
        f"# Source:   roles/apparmor/local_vars/customized_extra_dirs.yml\n"
        "#\n"
        f"{desc_lines}\n"
        "#\n"
        f"# Profiles that #include <abstractions/"
        f"local_mixin_customized_extra_dirs__for__{name}> get the rules below.\n"
    )
    rules: list[str] = []
    for entry in sorted(definitions, key=lambda e: e["path"]):
        allow_list = entry["allow"]
        allowed = (_ANY_SENTINEL in allow_list) or (name in allow_list)
        rules.append(_rule_for_entry(entry["path"], allowed))
    return header + "\n" + "\n".join(rules) + "\n"


def render_deny_all(definitions: list[dict[str, Any]]) -> str:
    """Render the deny-all abstraction: every listed directory is denied,
    regardless of its `allow` list. For profiles that must never touch any
    customized directory (e.g. container base profiles). Reads the SAME source
    as the per-category abstractions, so there is one source of truth."""
    header = (
        "# Managed by Ansible - do not edit manually\n"
        f"# Generated by roles/apparmor/scripts/gen_customized_extra_dirs_aa_mixins.py\n"
        "# Special: deny-all - every listed directory is denied, regardless of\n"
        "#          its allow list. Reads the same source as the per-category\n"
        "#          abstractions (one source of truth).\n"
        f"# Source:   roles/apparmor/local_vars/customized_extra_dirs.yml\n"
        "#\n"
        "# Include in profiles that must never touch any customized directory\n"
        "# (e.g. container base profiles):\n"
        f"#   #include <abstractions/{_DENY_ALL_ABSTRACTION_NAME}>\n"
    )
    rules = [
        _rule_for_entry(entry["path"], False)
        for entry in sorted(definitions, key=lambda e: e["path"])
    ]
    return header + "\n" + "\n".join(rules) + "\n"


def schema_path_for(definitions_file: Path) -> Path:
    """Companion schema path for a YAML file. e.g. foo.yml -> foo.schema.json.
    Sits next to the YAML so editor `yaml-language-server: $schema=./...`
    directives resolve to it."""
    return definitions_file.with_suffix(".schema.json")


def write_schema(definitions_file: Path, categories: list[dict[str, str]]) -> Path:
    """Write the JSON Schema next to the YAML and return its path."""
    schema_path = schema_path_for(definitions_file)
    schema_path.write_text(
        json.dumps(build_schema(categories), indent=2) + "\n",
        encoding="utf-8",
    )
    return schema_path


def build(
    definitions_file: Path,
    categories_file: Path,
    output_dir: Path,
) -> tuple[list[Path], Path]:
    """End-to-end: load, validate, render, write. Return (abstraction paths,
    schema path). The schema is always (re-)written so editors picking it up
    via `yaml-language-server: $schema=...` stay in sync with categories."""
    categories = load_categories(categories_file)
    schema = build_schema(categories)

    raw = definitions_file.read_text(encoding="utf-8")
    definitions = yaml.safe_load(raw)
    if definitions is None:
        definitions = []
    validate_definitions(definitions, schema)

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for category in categories:
        out_path = output_dir / f"local_mixin_customized_extra_dirs__for__{category['name']}"
        out_path.write_text(render_abstraction(category, definitions), encoding="utf-8")
        written.append(out_path)

    # Plus the category-agnostic deny-all, from the same definitions.
    deny_all_path = output_dir / _DENY_ALL_ABSTRACTION_NAME
    deny_all_path.write_text(render_deny_all(definitions), encoding="utf-8")
    written.append(deny_all_path)

    schema_path = write_schema(definitions_file, categories)
    return written, schema_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build per-category AppArmor abstractions from "
            "roles/apparmor/local_vars/customized_extra_dirs.yml."
        ),
    )
    parser.add_argument(
        "--in",
        dest="definitions",
        metavar="FILE",
        type=Path,
        default=_DEFAULT_DEFINITIONS_FILE,
        help=f"Definitions YAML (default: {_DEFAULT_DEFINITIONS_FILE}).",
    )
    parser.add_argument(
        "--categories",
        metavar="FILE",
        type=Path,
        default=_DEFAULT_CATEGORIES_FILE,
        help=f"Categories YAML (default: {_DEFAULT_CATEGORIES_FILE}).",
    )
    parser.add_argument(
        "--out",
        dest="output_dir",
        metavar="DIR",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--dump-schema",
        action="store_true",
        help="Print the JSON Schema to stdout and exit (for IDE/editor use).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help=(
            "Validate the definitions YAML against the schema, echo its "
            "content to stdout, and exit. Does not write abstractions or "
            "schema files. Use as a pre-flight check before running the "
            "playbook."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "Pre-flight for `make apply-apparmor`: probe + install "
            "`python3-jsonschema` if missing (via sudo), validate the "
            "definitions YAML, show the colored preview, and prompt for "
            "y/N. Exit 0 only on `y`/`yes`. Used so the heavy parts "
            "(install probe, validation, preview, confirmation) happen "
            "BEFORE ansible-playbook starts up, instead of mid-playbook."
        ),
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help=(
            "Colorize the --validate-only YAML preview. `auto` (default) "
            "enables color when stdout is a TTY and NO_COLOR is unset; "
            "`always` forces it on (useful when piping into another viewer "
            "that handles ANSI, e.g. ansible.builtin.pause)."
        ),
    )
    args = parser.parse_args()

    try:
        categories = load_categories(args.categories)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dump_schema:
        # Doesn't need jsonschema; skip the probe.
        print(json.dumps(build_schema(categories), indent=2))
        return

    # Everything past this point eventually calls validate_definitions(),
    # which lazy-imports the jsonschema module. Ensure the distro package
    # is installed first so this script is self-bootstrapping for every
    # caller (sandbox `_pre_flight`, `make apply-apparmor` pre-flight,
    # role's --validate-only and default build modes). Idempotent probe;
    # fast no-op when already present.
    _ensure_jsonschema()

    if not args.definitions.exists():
        print(
            f"error: definitions file not found: {args.definitions}\n"
            f"Run roles/apparmor/scripts/gen_customized_extra_dirs_definitions_yaml.py to scaffold one.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.validate_only or args.confirm:
        # Pre-flight check: load + validate, echo content, no writes.
        try:
            raw = args.definitions.read_text(encoding="utf-8")
            definitions = yaml.safe_load(raw)
            if definitions is None:
                definitions = []
            validate_definitions(definitions, build_schema(categories))
        except (OSError, ValueError, yaml.YAMLError) as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        color = resolve_color_mode(args.color)
        # Path on its own line so triple-click / double-click selects ONLY
        # the path (mixing prose like "# Contents of X:" breaks copy-paste).
        print("# Contents of:")
        print(args.definitions)
        print()
        print(colorize_preview(raw.rstrip(), color=color, star_sentinel=_ANY_SENTINEL))
        print()
        print(f"# OK - {len(definitions)} entr{'y' if len(definitions) == 1 else 'ies'}, schema-valid.")

        if args.confirm:
            print()
            try:
                reply = input("Proceed with applying the AppArmor profiles? [y/N] ").strip().lower()
            except EOFError:
                reply = ""
            if reply not in ("y", "yes"):
                print("Aborted by user.", file=sys.stderr)
                sys.exit(1)
        return

    try:
        written, schema_path = build(args.definitions, args.categories, args.output_dir)
    except (OSError, ValueError, yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {len(written)} abstraction(s) to {args.output_dir}:")
    for p in written:
        print(f"  {p.name}")
    print(f"Wrote JSON Schema: {schema_path}")


if __name__ == "__main__":
    main()
