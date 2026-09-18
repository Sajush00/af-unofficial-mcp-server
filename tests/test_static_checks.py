"""Tests for the static checks themselves: each rule fires on bad code.

These tests protect the checks from silently rotting: for every AF rule
there is a small violating source and a small clean source.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from static_checks import Violation, check_source, scan

REPO = Path(__file__).resolve().parents[1]


def run(source: str, *, filename: str = "mod.py") -> list[Violation]:
    return check_source(Path(filename), textwrap.dedent(source))


def rules(source: str, *, filename: str = "mod.py") -> set[str]:
    return {violation.rule for violation in run(source, filename=filename)}


# ------------------------------------------------------------------ AF001
def test_af001_fires_on_unguarded_system_exit():
    assert "AF001" in rules("raise SystemExit(1)\n")


def test_af001_allows_exit_inside_main_guard():
    source = """
        def main() -> int:
            return 0

        if __name__ == "__main__":
            raise SystemExit(main())
    """
    assert rules(source) == set()


# ------------------------------------------------------------------ AF002
def test_af002_fires_on_fixed_offset_timezone():
    source = """
        from datetime import timedelta, timezone
        SYDNEY = timezone(timedelta(hours=10))
    """
    assert "AF002" in rules(source)


def test_af002_allows_zoneinfo():
    source = """
        from zoneinfo import ZoneInfo
        SYDNEY = ZoneInfo("Australia/Sydney")
    """
    assert rules(source) == set()


# ------------------------------------------------------------------ AF003
def test_af003_fires_on_direct_clock_read():
    assert "AF003" in rules("from datetime import datetime\nX = datetime.now()\n")


def test_af003_allows_clock_read_in_timeutil():
    source = "from datetime import datetime\nX = datetime.now()\n"
    assert rules(source, filename="timeutil.py") == set()


# ------------------------------------------------------------------ AF004
def test_af004_fires_on_urllib_outside_http_module():
    assert "AF004" in rules("import urllib.request\n", filename="apis.py")


def test_af004_allows_urllib_inside_http_module():
    assert rules("import urllib.request\n", filename="http.py") == set()


# ------------------------------------------------------------------ AF005
def test_af005_fires_on_unbounded_visit_fetch():
    source = """
        def fetch(client):
            return client("me/membership/gym-visit", {"startDate": "x"})
    """
    assert "AF005" in rules(source)


def test_af005_fires_on_visit_literal_outside_a_call():
    assert "AF005" in rules('ENDPOINT = "me/membership/gym-visit"\n')


def test_af005_allows_a_bounded_fetch():
    source = """
        def fetch(client, start, end):
            return client("me/membership/gym-visit", {"startDate": start, "endDate": end})
    """
    assert rules(source) == set()


# ------------------------------------------------------------------ AF006
def test_af006_fires_on_undocumented_tool():
    source = """
        @mcp.tool()
        def mystery(x: int) -> dict:
            return {}
    """
    assert "AF006" in rules(source)


def test_af006_allows_documented_tool():
    source = '''
        @mcp.tool()
        def described(x: int) -> dict:
            """Do the thing."""
            return {}
    '''
    assert rules(source) == set()


# ------------------------------------------------------------------ AF007
def test_af007_fires_on_network_import_in_tests():
    assert "AF007" in rules("import socket\n", filename="tests/test_x.py")


def test_af007_allows_urllib_error_but_not_request():
    assert rules("import urllib.error\n", filename="tests/test_x.py") == set()


# ------------------------------------------------------------------ AF008
def test_af008_fires_on_builtin_raises():
    assert "AF008" in rules('raise ValueError("nope")\n')
    assert "AF008" in rules('raise RuntimeError("boom")\n')


def test_af008_allows_typed_errors():
    assert rules('raise ApiError(500, "boom", "/path")\n') == set()


# ------------------------------------------------------------------ AF009
def test_af009_fires_on_import_time_io():
    assert "AF009" in rules("TOKEN = access_token()\n")


def test_af009_allows_calls_inside_functions():
    source = """
        def main() -> str:
            return access_token()
    """
    assert rules(source) == set()


# ------------------------------------------------------------------ the repo
def test_the_repository_itself_is_clean():
    violations = scan([REPO / "src" / "af_mcp", REPO / "tests"])
    assert violations == [], "\n".join(str(violation) for violation in violations)
