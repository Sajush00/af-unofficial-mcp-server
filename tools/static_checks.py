"""Deterministic project checks: invariants ruff and mypy cannot express.

Every rule below encodes a failure this project has already hit once, and
its message says what to do instead. Run them directly:

    uv run python tools/static_checks.py

The same code runs inside the test suite (tests/test_static_checks.py), so
`make check` and ruff-only workflows both stay honest.

Rules:
    AF001  no process exits outside a __main__ guard
    AF002  no fixed-offset timezones, club time goes through timeutil
    AF003  clock reads happen only in timeutil
    AF004  urllib is imported only inside af_mcp/http.py
    AF005  every gym-visit fetch passes explicit startDate and endDate
    AF006  MCP tools carry docstrings (they become the agent-facing text)
    AF007  tests stay offline (network imports only in the offline guard)
    AF008  src raises typed errors from af_mcp.errors, never builtins
    AF009  src performs no network I/O at import time (module level)
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "af_mcp"
TESTS = REPO / "tests"

VISIT_ENDPOINT = "me/membership/gym-visit"
OFFLINE_BANNED_IMPORTS = ("urllib.request", "socket", "requests", "httpx", "http.client")
# The offline guard is the one test file that must import socket: it patches
# connect() and getaddrinfo() for the whole suite.
OFFLINE_ALLOWED_IMPORTS = {"conftest.py": {"socket"}}
BUILTIN_EXCEPTION_RAISES = frozenset(
    {
        "AssertionError",
        "BaseException",
        "Exception",
        "IOError",
        "KeyError",
        "NotImplementedError",
        "OSError",
        "RuntimeError",
        "TypeError",
        "ValueError",
    }
)
IMPORT_TIME_IO_CALLS = frozenset(
    {
        "access_token",
        "api_get",
        "request_json",
        "urlopen",
        "urlretrieve",
    }
)

MSG_EXIT = "process exit outside a __main__ guard; raise a typed AFError instead"
MSG_FIXED_OFFSET = "fixed-offset timezone(...) construction; use timeutil.club_zone() (DST-safe)"
MSG_CLOCK_READ = "direct {name}() clock read; use timeutil.now() so callers can inject the moment"
MSG_URLLIB = "import of {module}; network calls live behind af_mcp/http.py only"
MSG_VISIT_OUTSIDE = "visit endpoint outside a fetch call; pass startDate and endDate to api_get"
MSG_VISIT_MISSING = "visit fetch is missing {missing}; unbounded pulls grow agent context"
MSG_TOOL_DOC = "@mcp.tool {name}() has no docstring; it becomes the agent-facing description"
MSG_TEST_OFFLINE = "tests must stay offline (found {module}); use the fake_api fixture"
MSG_BUILTIN_RAISE = "raise {name}(...); use a typed error from af_mcp/errors.py"
MSG_IMPORT_TIME_IO = "module-level {name}() call; imports must not perform I/O"


@dataclass(frozen=True)
class Violation:
    rule: str
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


# ------------------------------------------------------------------ helpers
def _attr_chain(node: ast.AST) -> list[str]:
    """Flatten foo.bar.baz into ['foo', 'bar', 'baz'] (names only)."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return list(reversed(parts))


def _raised_name(node: ast.expr | None) -> str | None:
    """The class name in `raise X(...)` or `raise X`, else None."""
    if node is None:
        return None
    if isinstance(node, ast.Call):
        chain = _attr_chain(node.func)
        return chain[-1] if chain else None
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_main_guard(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _main_guard_spans(tree: ast.Module) -> list[tuple[int, int]]:
    return [
        (node.lineno, node.end_lineno or node.lineno)
        for node in tree.body
        if isinstance(node, ast.If) and _is_main_guard(node.test)
    ]


def _in_spans(spans: list[tuple[int, int]], line: int) -> bool:
    return any(start <= line <= end for start, end in spans)


def _imported_modules(tree: ast.Module) -> Iterator[tuple[str, int]]:
    """Every imported module name paired with its line number."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from ((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield (node.module, node.lineno)


def _module_level_nodes(tree: ast.Module) -> Iterator[ast.AST]:
    """Nodes executed at import time: below the module, but not into defs."""
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _string_keys(call: ast.Call) -> set[str]:
    keys: set[str] = set()
    for arg in [*call.args, *(kw.value for kw in call.keywords)]:
        if isinstance(arg, ast.Dict):
            for key in arg.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


# ------------------------------------------------------------------ checks
def check_no_unguarded_exit(path: Path, tree: ast.Module) -> list[Violation]:
    """AF001: library code raises typed errors, it never ends the process."""
    spans = _main_guard_spans(tree)
    out = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Raise)
            and _raised_name(node.exc) == "SystemExit"
            and not _in_spans(spans, node.lineno)
        ):
            out.append(Violation("AF001", path, node.lineno, MSG_EXIT))
        if (
            isinstance(node, ast.Call)
            and _attr_chain(node.func) == ["sys", "exit"]
            and not _in_spans(spans, node.lineno)
        ):
            out.append(Violation("AF001", path, node.lineno, MSG_EXIT))
    return out


def check_no_fixed_offsets(path: Path, tree: ast.Module) -> list[Violation]:
    """AF002: club-local time is a zone (DST-aware), never a fixed offset."""
    return [
        Violation("AF002", path, node.lineno, MSG_FIXED_OFFSET)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _attr_chain(node.func)[-1:] == ["timezone"] and node.args
    ]


def check_clock_reads(path: Path, tree: ast.Module) -> list[Violation]:
    """AF003: clock reads go through timeutil so tests can inject a moment."""
    if path.name == "timeutil.py":
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _attr_chain(node.func)
        if len(chain) < 2:
            continue
        name, owner = chain[-1], chain[-2]
        if name in ("now", "today", "utcnow") and owner in ("datetime", "date", "dt"):
            message = MSG_CLOCK_READ.format(name=name)
            out.append(Violation("AF003", path, node.lineno, message))
    return out


def check_http_seam(path: Path, tree: ast.Module) -> list[Violation]:
    """AF004: only af_mcp/http.py imports urllib (one network seam)."""
    if path.name == "http.py":
        return []
    return [
        Violation("AF004", path, lineno, MSG_URLLIB.format(module=module))
        for module, lineno in _imported_modules(tree)
        if module == "urllib" or module.startswith("urllib.")
    ]


def check_bounded_visits(path: Path, tree: ast.Module) -> list[Violation]:
    """AF005: visit fetches always carry explicit start and end bounds."""
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    out = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and VISIT_ENDPOINT in node.value
        ):
            continue
        call = parents.get(node)
        if not isinstance(call, ast.Call):
            out.append(Violation("AF005", path, node.lineno, MSG_VISIT_OUTSIDE))
            continue
        missing = {"startDate", "endDate"} - _string_keys(call)
        if missing:
            message = MSG_VISIT_MISSING.format(missing=sorted(missing))
            out.append(Violation("AF005", path, node.lineno, message))
    return out


def check_tool_docstrings(path: Path, tree: ast.Module) -> list[Violation]:
    """AF006: an MCP tool without a docstring is an undocumented agent API."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_tool = any(
            isinstance(dec, ast.Call) and _attr_chain(dec.func)[-1:] == ["tool"]
            for dec in node.decorator_list
        )
        if is_tool and not ast.get_docstring(node):
            out.append(Violation("AF006", path, node.lineno, MSG_TOOL_DOC.format(name=node.name)))
    return out


def check_typed_raises(path: Path, tree: ast.Module) -> list[Violation]:
    """AF008: src raises typed errors from af_mcp.errors, never builtins."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            name = _raised_name(node.exc)
            if name in BUILTIN_EXCEPTION_RAISES:
                out.append(
                    Violation("AF008", path, node.lineno, MSG_BUILTIN_RAISE.format(name=name))
                )
    return out


def check_no_import_time_io(path: Path, tree: ast.Module) -> list[Violation]:
    """AF009: importing a module must not perform network I/O."""
    out = []
    for node in _module_level_nodes(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _attr_chain(node.func)
        if chain and chain[-1] in IMPORT_TIME_IO_CALLS:
            message = MSG_IMPORT_TIME_IO.format(name=chain[-1])
            out.append(Violation("AF009", path, node.lineno, message))
    return out


def check_tests_offline(path: Path, tree: ast.Module) -> list[Violation]:
    """AF007: tests replay recorded shapes, they never open a connection."""
    allowed = OFFLINE_ALLOWED_IMPORTS.get(path.name, set())
    return [
        Violation("AF007", path, lineno, MSG_TEST_OFFLINE.format(module=module))
        for module, lineno in _imported_modules(tree)
        if module.startswith(OFFLINE_BANNED_IMPORTS) and module not in allowed
    ]


SRC_CHECKS = [
    check_no_unguarded_exit,
    check_no_fixed_offsets,
    check_clock_reads,
    check_http_seam,
    check_bounded_visits,
    check_tool_docstrings,
    check_typed_raises,
    check_no_import_time_io,
]
TEST_CHECKS = [check_tests_offline]


def _is_test_path(path: Path) -> bool:
    return path.name.startswith("test_") or path.parent.name == "tests"


def check_source(path: Path, source: str) -> list[Violation]:
    """Run the relevant checks over one source string (used by tests too)."""
    tree = ast.parse(source, filename=str(path))
    checks = TEST_CHECKS if _is_test_path(path) else SRC_CHECKS
    out: list[Violation] = []
    for check in checks:
        out.extend(check(path, tree))
    return out


def scan(roots: list[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for root in roots:
        files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
        for file in files:
            violations.extend(check_source(file, file.read_text()))
    return sorted(violations, key=lambda v: (str(v.path), v.line))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic project checks.")
    parser.add_argument("paths", nargs="*", type=Path, help="roots to scan (default: src + tests)")
    args = parser.parse_args(argv)
    roots = args.paths if args.paths else [SRC, TESTS]
    violations = scan(roots)
    for violation in violations:
        print(violation)
    scanned = sum(1 for root in roots for _ in root.rglob("*.py"))
    print(f"{len(violations)} violation(s) across {scanned} file(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
