"""Club directory: home gym, busy meter, and nearby search."""

from __future__ import annotations

from typing import Any

from af_mcp import transport
from af_mcp.errors import AFError


def home_gym() -> dict[str, Any]:
    """Return the home club profile (afNumber, name, coordinates, ...)."""
    data = transport.api_get("me/user/my-gym")
    return data["clubProfile"] if isinstance(data, dict) else data


def busy_meter(af_number: str) -> dict[str, Any]:
    """Return the busy-meter payload for one club (live count + week averages)."""
    return transport.api_get(f"clubs/{af_number}/busy-meter")


def resolve_club(af_number: str | None) -> tuple[str, str]:
    """Return (af_number, name), defaulting to the home gym."""
    if af_number:
        return af_number, af_number
    gym = home_gym()
    return gym["afNumber"], gym["name"]


def day_usages(data: dict[str, Any], weekday: str) -> list[dict[str, Any]]:
    """The hourly average rows for one weekday name, sorted by start time."""
    for day in data.get("weekDays") or []:
        if day["weekDay"] == weekday:
            return sorted(day["averageUsages"], key=lambda usage: usage["startTime"])
    return []


def nearby(radius_km: int, limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (home gym, clubs near it, nearest first, each with a live count).

    Live counts are best effort: when the batch call fails the club list is
    still returned with currentMemberCount=None.
    """
    gym = home_gym()
    results = (
        transport.api_get(
            "location/search",
            {
                "latitude": gym["coordinates"]["latitude"],
                "longitude": gym["coordinates"]["longitude"],
                "unitSystem": "Metric",
                "radius": radius_km,
                "page": 1,
                "pageSize": limit,
            },
        )
        or []
    )
    counts = _live_counts([club["locationNumber"] for club in results])
    return gym, [
        {
            "afNumber": club["locationNumber"],
            "name": club["name"],
            "distanceKm": round(club.get("distance", {}).get("value", 0), 1),
            "status": club.get("status", {}).get("description"),
            "isOpen24Hours": club.get("isOpen24Hours"),
            "address": ", ".join(
                filter(
                    None,
                    [
                        club["address"]["address"],
                        club["address"]["city"],
                    ],
                )
            ),
            "currentMemberCount": counts.get(club["locationNumber"]),
            "isHomeGym": club["locationNumber"] == gym["afNumber"],
        }
        for club in results
    ]


def _live_counts(af_numbers: list[str]) -> dict[str, int | None]:
    if not af_numbers:
        return {}
    params = [("afNumbers", number) for number in af_numbers]
    try:
        batch = transport.api_get("clubs/busy-meter", params)
    except AFError:
        # Live counts are best effort by design; the club list still returns.
        return {}
    return {entry.get("afNumber"): entry.get("currentMemberCount") for entry in batch or []}
