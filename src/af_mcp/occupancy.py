"""Occupancy, forecast, and go-now verdict builders."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from af_mcp import clubs, timeutil
from af_mcp.errors import InvalidInputError

# ratio of live count to the typical count for this hour
VERDICT_BANDS = (
    (0.50, "go-now"),
    (0.85, "good-time"),
    (1.15, "normal"),
    (1.50, "wait"),
)


def occupancy(af_number: str | None = None, *, now: datetime | None = None) -> dict:
    """Live headcount now plus typical counts for the rest of the local day."""
    af_number, name = clubs.resolve_club(af_number)
    data = clubs.busy_meter(af_number)
    moment = timeutil.local(now or timeutil.now())
    count = data.get("currentMemberCount")
    peak = data.get("maxAverageUsage")
    return {
        "afNumber": af_number,
        "name": name,
        "currentMemberCount": count,
        "maxAverageUsage": peak,
        "busyPercent": (round(100 * count / peak, 1) if count is not None and peak else None),
        "restOfDay": [
            {"hour": usage["startTime"][:5], "typicalCount": usage["averageUsageValue"]}
            for usage in clubs.day_usages(data, moment.strftime("%A"))
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


def go_now_verdict(*, now: datetime | None = None) -> dict:
    """Live count vs the typical count for this hour, as a verdict."""
    af_number, name = clubs.resolve_club(None)
    data = clubs.busy_meter(af_number)
    moment = timeutil.local(now or timeutil.now())
    count = data.get("currentMemberCount")
    if count is None:
        return {
            "afNumber": af_number,
            "name": name,
            "verdict": "no-live-data",
            "message": "This club has no live occupancy right now.",
        }
    typical = None
    for usage in clubs.day_usages(data, moment.strftime("%A")):
        if int(usage["startTime"][:2]) == moment.hour:
            typical = usage["averageUsageValue"]
            break
    if not typical:
        return {
            "afNumber": af_number,
            "name": name,
            "currentMemberCount": count,
            "verdict": "no-baseline",
            "message": "No typical baseline for this hour.",
        }
    ratio = count / typical
    verdict = "skip"
    for ceiling, name_ in VERDICT_BANDS:
        if ratio <= ceiling:
            verdict = name_
            break
    return {
        "afNumber": af_number,
        "name": name,
        "timestamp": moment.isoformat(timespec="minutes"),
        "currentMemberCount": count,
        "typicalCount": typical,
        "ratio": round(ratio, 2),
        "verdict": verdict,
    }


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
