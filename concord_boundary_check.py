#!/usr/bin/env python3
"""
Concord boundary checker — NR.2 reference implementation.

Enforces the contract/mechanics split (Decisions 5, 8 in the architecture plan):

    concord/core/               : pure functional core. No runtime imports.
    concord/domain/             : domain types and services. No runtime imports.
    concord/runtime/protocol.py : runtime-agnostic protocol definitions.
    concord/runtime/dbos.py     : the only file allowed to import `dbos`.
    concord/runtime/temporal.py : the only file allowed to import `temporalio`.
                                  (future; same rule shape.)

Usage:

    python concord_boundary_check.py concord/
    python concord_boundary_check.py concord/ --extra-runtime temporalio:concord/runtime/temporal.py

CI integration (GitHub Actions):

    - name: Concord boundary check
      run: python tools/concord_boundary_check.py concord/

Exit codes:
    0 — no violations
    1 — violations found
    2 — invalid arguments / path errors
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoundaryRule:
    """A single import-allowed-or-not rule, evaluated per file."""

    name: str
    # Predicate over the file's POSIX path inside the project.
    applies_when: callable
    disallowed_module_prefixes: tuple[str, ...]
    rationale: str


def default_rules() -> list[BoundaryRule]:
    """Concord's default boundary rules.

    Each rule says: 'for files matching this predicate, none of these module
    prefixes may appear as imports.' A module prefix matches `foo` or `foo.*`.
    """
    return [
        BoundaryRule(
            name="functional-core",
            applies_when=lambda p: "/concord/core/" in p.as_posix() + "/",
            disallowed_module_prefixes=("dbos", "temporalio"),
            rationale=(
                "concord/core/ is the pure functional core. "
                "It must not import any runtime — DBOS, Temporal, or otherwise."
            ),
        ),
        BoundaryRule(
            name="domain-layer",
            applies_when=lambda p: "/concord/domain/" in p.as_posix() + "/",
            disallowed_module_prefixes=("dbos", "temporalio"),
            rationale=(
                "concord/domain/ may import the runtime *protocol* "
                "(concord.runtime.protocol) but never a runtime implementation."
            ),
        ),
        BoundaryRule(
            name="runtime-adapter-isolation-dbos",
            applies_when=lambda p: (
                "/concord/runtime/" in p.as_posix() + "/"
                and p.name not in {"dbos.py", "__init__.py"}
                and not p.name.startswith("test_")
            ),
            disallowed_module_prefixes=("dbos",),
            rationale=(
                "Only concord/runtime/dbos.py may import `dbos`. "
                "All other runtime-layer modules must speak the protocol."
            ),
        ),
        BoundaryRule(
            name="runtime-adapter-isolation-temporal",
            applies_when=lambda p: (
                "/concord/runtime/" in p.as_posix() + "/"
                and p.name not in {"temporal.py", "__init__.py"}
                and not p.name.startswith("test_")
            ),
            disallowed_module_prefixes=("temporalio",),
            rationale=(
                "Only concord/runtime/temporal.py may import `temporalio`. "
                "All other runtime-layer modules must speak the protocol."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# AST traversal
# ---------------------------------------------------------------------------

def imports_in_file(path: Path) -> list[tuple[int, str]]:
    """Return (line, module_name) for every import in `path`. Empty on parse errors."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Skip unparseable files; not our job to lint syntax.
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.lineno, node.module))
    return out


def module_matches(imported: str, prefix: str) -> bool:
    """True if `imported` is exactly `prefix` or a submodule of it."""
    return imported == prefix or imported.startswith(prefix + ".")


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    imported_module: str
    rule: BoundaryRule

    def render(self) -> str:
        return (
            f"{self.path}:{self.lineno}\n"
            f"    imports `{self.imported_module}`\n"
            f"    violates rule: {self.rule.name}\n"
            f"    {self.rule.rationale}\n"
        )


def check_file(path: Path, rules: list[BoundaryRule]) -> list[Violation]:
    violations: list[Violation] = []
    matched_rules = [r for r in rules if r.applies_when(path)]
    if not matched_rules:
        return violations
    for lineno, imported in imports_in_file(path):
        for rule in matched_rules:
            if any(
                module_matches(imported, pfx)
                for pfx in rule.disallowed_module_prefixes
            ):
                violations.append(
                    Violation(
                        path=path,
                        lineno=lineno,
                        imported_module=imported,
                        rule=rule,
                    )
                )
    return violations


def check_tree(roots: list[Path], rules: list[BoundaryRule]) -> list[Violation]:
    all_violations: list[Violation] = []
    for root in roots:
        if not root.exists():
            print(f"warning: path does not exist: {root}", file=sys.stderr)
            continue
        for path in sorted(root.rglob("*.py")):
            all_violations.extend(check_file(path, rules))
    return all_violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce Concord's contract/mechanics import boundaries.",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=["concord"],
        help="Directories to scan (default: concord/).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress 'OK' line on success.",
    )
    args = parser.parse_args(argv)

    roots = [Path(r) for r in args.roots]
    violations = check_tree(roots, default_rules())

    if violations:
        print(f"\nConcord boundary check: {len(violations)} violation(s)\n")
        for v in violations:
            print(v.render())
        print(
            "FAIL: import boundaries violated. "
            "See https://concord.dev/boundaries (or the plan file) for the rationale.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print("OK: no boundary violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
