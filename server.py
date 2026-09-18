#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["fastmcp>=2.0"]
# ///
"""AF Unofficial MCP Server — Anytime Fitness data as MCP tools.

Exposes the Anytime Fitness client (`af_api.py`) over the
Model Context Protocol so any MCP-compatible agent can answer gym questions:
live occupancy, typical busy patterns, nearby clubs, visit history.

Transport: stdio.  Run with:  uv run server.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import af_api

LOGIN_HINT = (
    "No usable Anytime Fitness session. Run once: "
    "`uv run af_api.py login --phone <number>` then `uv run af_api.py verify --code <code>`."
)

mcp = FastMCP(
    name="AF Gym",
    instructions=(
        "Read-only, personal Anytime Fitness data. Each call fetches fresh data from "
        "the AF mobile API. Occupancy counts are live door-access numbers; 'typical' "
        "values are 100-day hourly averages in club-local time."
    ),
)


def _call(fn, *args, **kwargs):
    """Run an af_api client function, surfacing its failures as MCP tool errors."""
    try:
        return fn(*args, **kwargs)
    except RuntimeError as exc:
        raise ToolError(str(exc).strip() or "AF API request failed") from exc
    except SystemExit as exc:
        detail = str(exc).strip() or "not logged in"
        raise ToolError(f"{detail} {LOGIN_HINT}") from exc


@mcp.tool()
def occupancy(club: str | None = None) -> dict:
    """Live headcount in the gym right now, plus typical counts for the rest of today.

    Args:
        club: AF club number like "AU-0000". Defaults to the home gym.
    """
    return _call(af_api.build_occupancy, club)


@mcp.tool()
def forecast(day: str = "tomorrow", club: str | None = None) -> dict:
    """Typical hourly busy pattern for a day (100-day rolling averages, club-local time).

    Args:
        day: "today", "tomorrow", or a weekday name like "saturday". Defaults to "tomorrow".
        club: AF club number like "AU-0000". Defaults to the home gym.
    """
    return _call(af_api.build_forecast, day, club)


@mcp.tool()
def go_now_verdict() -> dict:
    """Decide whether now is a good time to go to the gym.

    Compares the live headcount to the typical count for this hour and returns a
    verdict: go-now, good-time, normal, wait or skip, with the underlying numbers.
    """
    return _call(af_api.build_recommendation)


@mcp.tool()
def nearby_clubs(radius_km: int = 25, limit: int = 5) -> dict:
    """Clubs near the home gym, nearest first, each with distance and a live headcount.

    Args:
        radius_km: Search radius in kilometres around the home gym.
        limit: Maximum number of clubs to return.
    """
    gym, clubs = _call(af_api.fetch_nearby, radius_km, limit)
    return {
        "homeGym": {"afNumber": gym["afNumber"], "name": gym["name"]},
        "clubs": clubs,
    }


@mcp.tool()
def visit_stats(months: int = 12) -> dict:
    """Visit history for the personal account.

    Returns totals, the most common day and hour, the last visit, and a
    weekday x hour heatmap.

    Args:
        months: How far back to look, in months.
    """
    return _call(af_api.build_visit_stats, months)


def _parse_local_bound(value: str, *, end_of_day: bool) -> datetime:
    """Parse 'YYYY-MM-DD' (club-local, snapped to the day edge for that side) or an ISO datetime."""
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(
            f"Bad date {value!r}: use 'YYYY-MM-DD' or an ISO datetime like '2026-09-01T18:00'."
        ) from exc
    if parsed.tzinfo is None:
        if len(text) <= 10:  # bare date: cover the whole club-local day
            parsed = parsed.replace(
                hour=23 if end_of_day else 0,
                minute=59 if end_of_day else 0,
                second=59 if end_of_day else 0,
            )
        parsed = parsed.replace(tzinfo=af_api.SYDNEY)
    return parsed


def _visits_in_window(start: datetime, end: datetime) -> list[tuple[datetime, str | None]]:
    """(club-local datetime, club name) pairs for [start, end], oldest first.

    Only the requested window is fetched, so queries never pull the full history.
    """
    raw = _call(af_api.api_get, "me/membership/gym-visit", {
        "startDate": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDate": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    if not isinstance(raw, list):
        return []
    visits = [
        (af_api.parse_utc(v["timestamp"]).astimezone(af_api.SYDNEY), v.get("homeClubDisplayName"))
        for v in raw
        if isinstance(v, dict) and v.get("timestamp")
    ]
    visits.sort(key=lambda pair: pair[0])
    return visits


DEFAULT_WINDOW_DAYS = 90
WIDEN_WINDOW_DAYS = 730


@mcp.tool()
def visit_history(start: str | None = None, end: str | None = None, count: int = 20) -> dict:
    """Gym check-ins in a date range, newest first, with totals for the range.

    Defaults to the last 90 days. Prefer a range over pulling all history:
    "visits in August" is start "2026-08-01", end "2026-08-31" (count 1 when
    only the total matters). When the range reaches today it also reports days
    since the last visit and, when the window is wide enough, 7/30-day counts.
    Dates are club-local (Sydney) and inclusive.

    Args:
        start: Range start, inclusive. Default: 90 days before end.
        end: Range end, inclusive; a bare date covers the whole day. Default: now.
        count: Max visits to list, newest first (default 20, max 200).
    """
    count = max(1, min(int(count), 200))
    now = datetime.now(timezone.utc)
    end_dt = _parse_local_bound(end, end_of_day=True) if end else now
    start_dt = (
        _parse_local_bound(start, end_of_day=False) if start
        else end_dt - timedelta(days=DEFAULT_WINDOW_DAYS)
    )
    if start_dt > end_dt:
        raise ToolError(f"start ({start_dt:%Y-%m-%d %H:%M}) is after end ({end_dt:%Y-%m-%d %H:%M}).")

    visits = _visits_in_window(start_dt, end_dt)
    widened = None
    if not visits and start is None and end is None:
        widened = _visits_in_window(now - timedelta(days=WIDEN_WINDOW_DAYS), now)

    now_local = now.astimezone(af_api.SYDNEY)
    local_date = now_local.date()

    def days_ago(then: datetime) -> int:
        return (local_date - then.date()).days

    result: dict = {
        "range": {
            "start": start_dt.astimezone(af_api.SYDNEY).strftime("%Y-%m-%d"),
            "end": end_dt.astimezone(af_api.SYDNEY).strftime("%Y-%m-%d"),
        },
        "totalInRange": len(visits),
        "shown": 0,
        "truncated": False,
        "visits": [],
    }
    if widened is not None:
        result["note"] = (
            f"No visits in the last {DEFAULT_WINDOW_DAYS} days; "
            "lastVisit is the most recent visit on record."
            if widened
            else f"No visits in the last {WIDEN_WINDOW_DAYS} days."
        )
    latest = visits[-1] if visits else (widened[-1] if widened else None)
    if latest and end_dt >= now:
        result["lastVisit"] = latest[0].strftime("%Y-%m-%d %H:%M")
        result["daysSinceLastVisit"] = days_ago(latest[0])
        if visits:
            if start_dt <= now - timedelta(days=7):
                result["last7Days"] = sum(1 for t, _ in visits if days_ago(t) < 7)
            if start_dt <= now - timedelta(days=30):
                result["last30Days"] = sum(1 for t, _ in visits if days_ago(t) < 30)
    if visits:
        shown = visits[-count:]
        result["shown"] = len(shown)
        result["truncated"] = len(shown) < len(visits)
        result["visits"] = [
            {
                "local": t.strftime("%Y-%m-%d %H:%M"),
                "weekday": t.strftime("%A"),
                "daysAgo": days_ago(t),
                "club": club,
            }
            for t, club in reversed(shown)
        ]
    return result


@mcp.tool()
def auth_status() -> dict:
    """Report whether a saved Anytime Fitness session exists and still refreshes.

    Returns only metadata. Token values are never returned.
    """
    try:
        af_api.get_access_token()
    except (SystemExit, RuntimeError) as exc:
        return {"loggedIn": False, "detail": str(exc).strip() or LOGIN_HINT}
    token = json.loads(af_api.TOKEN_FILE.read_text())
    expires_at = token.get("expires_at")
    return {
        "loggedIn": True,
        "accessTokenExpires": (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(expires_at)) if expires_at else None
        ),
        "autoRefresh": bool(token.get("RefreshToken")),
    }


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
