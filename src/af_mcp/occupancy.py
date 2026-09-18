"""Occupancy and forecast: the live picture and the go-now verdict."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from af_mcp import clubs, timeutil
from af_mcp.errors import InvalidInputError

# ratio of live count to the typical count for this hour
VERDICT_BANDS = (
    (0.50, "go-now"),
    (0.85, "good-time"),
    (1.15, "normal"),
    (1.50, "wait"),
)
VERDICT_MESSAGES = {
    "go-now": "Much quieter than usual. Go now.",
    "good-time": "Quieter than usual. Good time to go.",
    "normal": "About normal for this hour.",
    "wait": "Busier than usual. Maybe wait an hour.",
    "skip": "Unusually packed. Skip it if you can.",
    "no-live-data": "This club has no live occupancy right now.",
    "no-baseline": "No typical baseline for this hour.",
}


def occupancy(af_number: str | None = None, *, now: datetime | None = None) -> dict:
    """Live headcount, the go-now verdict, and typicals for the rest of today."""
    af_number, name = clubs.resolve_club(af_number)
    data = clubs.busy_meter(af_number)
    moment = timeutil.local(now or timeutil.now())
    usages = clubs.day_usages(data, moment.strftime("%A"))
    count = data.get("currentMemberCount")
    typical = _typical_for_hour(usages, moment.hour)
    verdict, ratio = _assess(count, typical)
    return {
        "afNumber": af_number,
        "name": name,
        "timestamp": moment.isoformat(timespec="minutes"),
        "currentMemberCount": count,
        "verdict": verdict,
        "verdictMessage": VERDICT_MESSAGES[verdict],
        "typicalCount": typical,
        "ratio": None if ratio is None else round(ratio, 2),
        "restOfDay": [
            {"hour": usage["startTime"][:5], "typicalCount": usage["averageUsageValue"]}
            for usage in usages
            if int(usage["startTime"][:2]) >= moment.hour
        ],
    }


def forecast(
    day: str = "tomorrow", af_number: str | None = None, *, now: datetime | None = None
) -> dict:
    """Typical hourly busy pattern for a day (100-day averages, club-local)."""
    af_number, name = clubs.resolve_club(af_number)
    data = clubs.busy_meter(af_number)
    target = _resolve_day(day, timeutil.local(now or timeutil.now()).date())
    usages = clubs.day_usages(data, target.strftime("%A"))
    return {
        "afNumber": af_number,
        "name": name,
        "date": target.isoformat(),
        "weekday": target.strftime("%A"),
        "hours": [
            {"hour": usage["startTime"][:5], "typicalCount": usage["averageUsageValue"]}
            for usage in usages
        ],
    }


def _typical_for_hour(usages: list[dict[str, Any]], hour: int) -> int | None:
    """The typical count for a given hour from the day's usage rows."""
    for usage in usages:
        if int(usage["startTime"][:2]) == hour:
            return usage["averageUsageValue"]
    return None


def _assess(count: int | None, typical: int | None) -> tuple[str, float | None]:
    """Verdict label and live/typical ratio for the given numbers."""
    if count is None:
        return "no-live-data", None
    if not typical:
        return "no-baseline", None
    ratio = count / typical
    label = next((name for ceiling, name in VERDICT_BANDS if ratio <= ceiling), "skip")
    return label, ratio


def _resolve_day(day: str, today: date) -> date:
    """Resolve 'today', 'tomorrow', or a weekday name into a date."""
    lowered = day.lower()
    if lowered == "today":
        return today
    if lowered == "tomorrow":
        return today + timedelta(days=1)
    for offset in range(7):
        candidate = today + timedelta(days=offset)
        if candidate.strftime("%A").lower() == lowered:
            return candidate
    raise InvalidInputError(f"Unknown day {day!r} (use 'today', 'tomorrow', or a weekday name)")
