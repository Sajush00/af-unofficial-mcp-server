"""Visit history: bounded window fetches and range summaries.

Every query sends an explicit [startDate, endDate] pair (enforced by static
check AF005). The endpoint accepts dates back to account creation, so an
unbounded fetch is one missing parameter away; that default is gone on
purpose, whole-history pulls bloat agent context for no benefit.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from af_mcp import timeutil, transport
from af_mcp.errors import InvalidInputError

DEFAULT_WINDOW_DAYS = 90
WIDEN_WINDOW_DAYS = 730
MAX_LISTED = 200


@dataclass(frozen=True)
class Visit:
    """One check-in, in club-local time."""

    at: datetime
    club: str | None


def fetch_window(start: datetime, end: datetime) -> list[Visit]:
    """Fetch visits in [start, end] inclusive; oldest first.

    Both bounds are always sent, so queries can never pull the full history.
    """
    raw = transport.api_get(
        "me/membership/gym-visit",
        {
            "startDate": timeutil.to_utc(start),
            "endDate": timeutil.to_utc(end),
        },
    )
    if not isinstance(raw, list):
        return []
    visits = [
        Visit(
            at=timeutil.local(timeutil.parse_utc(v["timestamp"])), club=v.get("homeClubDisplayName")
        )
        for v in raw
        if v.get("timestamp")
    ]
    visits.sort(key=lambda visit: visit.at)
    return visits


def visits(
    start: str | None = None,
    end: str | None = None,
    count: int = 20,
    *,
    now: datetime | None = None,
) -> dict:
    """Check-ins in a date range, newest first, with totals and habits.

    Defaults to the last 90 days. When the range is empty and both ends were
    defaulted, widens once to find the most recent visit on record.
    """
    count = max(1, min(int(count), MAX_LISTED))
    moment = timeutil.now() if now is None else now
    end_dt = timeutil.parse_bound(end, end_of_day=True) if end else moment
    start_dt = (
        timeutil.parse_bound(start, end_of_day=False)
        if start
        else end_dt - timedelta(days=DEFAULT_WINDOW_DAYS)
    )
    if start_dt > end_dt:
        raise InvalidInputError(
            f"start ({timeutil.moment_string(start_dt)}) is after end "
            f"({timeutil.moment_string(end_dt)})."
        )

    found = fetch_window(start_dt, end_dt)
    widened: list[Visit] | None = None
    if not found and start is None and end is None:
        widened = fetch_window(moment - timedelta(days=WIDEN_WINDOW_DAYS), moment)

    result: dict = {
        "range": {
            "start": timeutil.date_string(start_dt),
            "end": timeutil.date_string(end_dt),
        },
        "totalInRange": len(found),
        "shown": 0,
        "truncated": False,
        "visits": [],
        "timezone": str(timeutil.club_zone()),
    }
    if widened is not None:
        result["note"] = (
            f"No visits in the last {DEFAULT_WINDOW_DAYS} days; "
            "lastVisit is the most recent visit on record."
            if widened
            else f"No visits in the last {WIDEN_WINDOW_DAYS} days."
        )
    latest = found[-1] if found else (widened[-1] if widened else None)
    if latest and end_dt >= moment:
        result["lastVisit"] = timeutil.moment_string(latest.at)
        result["daysSinceLastVisit"] = timeutil.days_ago(latest.at, reference=moment)
        if found:
            if start_dt <= moment - timedelta(days=7):
                result["last7Days"] = sum(
                    1 for visit in found if timeutil.days_ago(visit.at, reference=moment) < 7
                )
            if start_dt <= moment - timedelta(days=30):
                result["last30Days"] = sum(
                    1 for visit in found if timeutil.days_ago(visit.at, reference=moment) < 30
                )
    if found:
        shown = found[-count:]
        result["shown"] = len(shown)
        result["truncated"] = len(shown) < len(found)
        result["visits"] = [
            {
                "local": timeutil.moment_string(visit.at),
                "weekday": visit.at.strftime("%A"),
                "daysAgo": timeutil.days_ago(visit.at, reference=moment),
                "club": visit.club,
            }
            for visit in reversed(shown)
        ]
        by_day = Counter(visit.at.strftime("%a") for visit in found)
        by_hour = Counter(visit.at.hour for visit in found)
        day, day_count = by_day.most_common(1)[0]
        hour, hour_count = by_hour.most_common(1)[0]
        result["mostCommonDay"] = {"day": day, "visits": day_count}
        result["mostCommonHour"] = {"hour": f"{hour:02d}:00", "visits": hour_count}
    return result
