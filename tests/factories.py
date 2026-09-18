"""Payload builders matching the shapes the mobile API returns."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def hour_row(start: str, value: int) -> dict[str, Any]:
    return {"startTime": start, "endTime": start, "averageUsageValue": value}


def week(usages_by_day: dict[str, list[tuple[str, int]]]) -> list[dict[str, Any]]:
    return [
        {"weekDay": day, "averageUsages": [hour_row(start, value) for start, value in rows]}
        for day, rows in usages_by_day.items()
    ]


def busy_meter(
    *,
    af_number: str = "AU-0000",
    current: int | None = 12,
    peak: int | None = 48,
    days: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "afNumber": af_number,
        "currentMemberCount": current,
        "maxAverageUsage": peak,
        "daysAggregatedCount": 100,
        "weekDays": days or [],
    }


def visits(entries: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"timestamp": ts, "homeClubDisplayName": club} for ts, club in entries]


def home_gym(*, af_number: str = "AU-0000", name: str = "Example Club") -> dict[str, Any]:
    return {
        "clubProfile": {
            "afNumber": af_number,
            "name": name,
            "coordinates": {"latitude": -33.8688, "longitude": 151.2093},
        }
    }


def search_results(*, numbers: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "locationNumber": number,
            "name": f"Club {number}",
            "distance": {"value": 1.5 + index},
            "status": {"description": "Club open"},
            "isOpen24Hours": True,
            "address": {"address": f"{index + 1} Test Street", "city": "Testville"},
        }
        for index, number in enumerate(numbers)
    ]


def busy_batch(*, numbers: list[str]) -> list[dict[str, Any]]:
    return [
        {"afNumber": number, "currentMemberCount": 5 + index}
        for index, number in enumerate(numbers)
    ]


def write_token(
    dir_path: Path,
    *,
    access: str = "test-access",
    refresh: str | None = "test-refresh",
    expires_in: float = 3600,
) -> Path:
    token_file = dir_path / "token.json"
    token_file.write_text(
        json.dumps(
            {
                "AccessToken": access,
                "RefreshToken": refresh,
                "expires_at": time.time() + expires_in,
            }
        )
    )
    return token_file


def read_token(dir_path: Path) -> dict[str, Any]:
    return json.loads((dir_path / "token.json").read_text())
