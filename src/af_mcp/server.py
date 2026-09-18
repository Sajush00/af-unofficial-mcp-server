"""AF Gym MCP server: Anytime Fitness data as MCP tools (stdio transport)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from af_mcp import auth
from af_mcp.clubs import nearby
from af_mcp.errors import AFError, LoginRequiredError
from af_mcp.occupancy import forecast as build_forecast
from af_mcp.occupancy import occupancy as build_occupancy
from af_mcp.visits import visits as build_visits

mcp = FastMCP(
    name="AF Gym",
    instructions=(
        "Read-only, personal Anytime Fitness data. Each call fetches fresh data from "
        "the AF mobile API. Occupancy counts are live door-access numbers; 'typical' "
        "values are 100-day hourly averages in club-local time. If a call reports no "
        "usable session, ask the user to run `af-gym login --phone <number>` in their "
        "terminal."
    ),
)

T = TypeVar("T")


def _run(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Translate client failures into MCP tool errors."""
    try:
        return fn(*args, **kwargs)
    except LoginRequiredError as exc:
        raise ToolError(str(exc).strip() or auth.LOGIN_HINT) from exc
    except AFError as exc:
        raise ToolError(str(exc).strip() or "AF request failed") from exc


@mcp.tool()
def occupancy(club: str | None = None) -> dict:
    """Live headcount right now, a go-now verdict, and typical counts for the rest of today.

    The verdict compares the live count to the typical count for this hour:
    go-now, good-time, normal, wait or skip (see verdictMessage). restOfDay
    lists the typical count for each remaining hour of today.

    Args:
        club: AF club number like "AU-0000". Defaults to the home gym.
    """
    return _run(build_occupancy, club)


@mcp.tool()
def forecast(day: str = "tomorrow", club: str | None = None) -> dict:
    """Typical hourly busy pattern for a day (100-day rolling averages, club-local time).

    Args:
        day: "today", "tomorrow", or a weekday name like "saturday". Defaults to "tomorrow".
        club: AF club number like "AU-0000". Defaults to the home gym.
    """
    return _run(build_forecast, day, club)


@mcp.tool()
def nearby_clubs(radius_km: int = 25, limit: int = 5) -> dict:
    """Clubs near the home gym, nearest first, each with distance and a live headcount.

    Args:
        radius_km: Search radius in kilometres around the home gym.
        limit: Maximum number of clubs to return.
    """
    gym, clubs = _run(nearby, radius_km, limit)
    return {
        "homeGym": {"afNumber": gym["afNumber"], "name": gym["name"]},
        "clubs": clubs,
    }


@mcp.tool()
def visits(start: str | None = None, end: str | None = None, count: int = 20) -> dict:
    """Gym check-ins in a date range, newest first, with totals and habits.

    Defaults to the last 90 days. Prefer a range over pulling all history:
    "visits in August" is start "2026-08-01", end "2026-08-31" (count 1 when
    only the total matters). When the range reaches today it also reports days
    since the last visit and, when the window is wide enough, 7/30-day counts;
    it always reports the most common day and hour in the range. Dates are
    club-local and inclusive.

    Args:
        start: Range start, inclusive. Default: 90 days before end.
        end: Range end, inclusive; a bare date covers the whole day. Default: now.
        count: Max visits to list, newest first (default 20, max 200).
    """
    return _run(build_visits, start, end, count)


@mcp.tool()
def auth_status() -> dict:
    """Report whether a saved Anytime Fitness session exists and still refreshes.

    Returns only metadata; token values are never returned. When this or any
    other call reports no usable session, ask the user to run
    `af-gym login --phone <number>` in their terminal.
    """
    return auth.status()


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
