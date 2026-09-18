"""Tests for visit history: bounded windows, summaries, widen fallback."""

from __future__ import annotations

import pytest

from af_mcp import timeutil, visits
from af_mcp.errors import InvalidInputError
from factories import visits as visits_payload

NOW = timeutil.parse_bound("2026-09-18T14:00", end_of_day=False)


def test_fetch_window_sends_both_bounds(fake_api, auth_env):
    fake_api.route("gym-visit", visits_payload([("2026-09-10T02:16:19Z", "Example Club")]))
    visits.fetch_window(NOW.replace(day=1), NOW)
    url = fake_api.calls[0]["url"]
    assert "startDate=" in url and "endDate=" in url


def test_fetch_window_sorts_oldest_first(fake_api, auth_env):
    fake_api.route(
        "gym-visit",
        visits_payload(
            [
                ("2026-09-10T02:16:19Z", "Example Club"),
                ("2026-09-01T01:00:00Z", "Example Club"),
            ]
        ),
    )
    rows = visits.fetch_window(NOW.replace(day=1), NOW)
    assert [row.at.day for row in rows] == [1, 10]


def test_default_window_is_90_days(fake_api, auth_env):
    fake_api.route("gym-visit", visits_payload([("2026-09-10T02:16:19Z", "Example Club")]))
    result = visits.visits(now=NOW)
    assert result["range"] == {"start": "2026-06-20", "end": "2026-09-18"}


def test_explicit_range_reports_totals_and_counts(fake_api, auth_env):
    fake_api.route(
        "gym-visit",
        visits_payload(
            [
                ("2026-08-07T09:52:00Z", "Example Club"),
                ("2026-08-20T12:27:00Z", "Example Club"),
                ("2026-08-25T10:33:00Z", "Example Club"),
            ]
        ),
    )
    result = visits.visits("2026-08-01", "2026-08-31", count=2, now=NOW)
    assert result["range"] == {"start": "2026-08-01", "end": "2026-08-31"}
    assert result["totalInRange"] == 3
    assert result["shown"] == 2
    assert result["truncated"] is True
    # newest first: the listing starts with the most recent visit
    assert result["visits"][0]["local"] == "2026-08-25 20:33"
    assert result["visits"][1]["local"] == "2026-08-20 22:27"
    # a past window reports no live "last visit" fields
    assert "lastVisit" not in result
    assert "daysSinceLastVisit" not in result


def test_live_counters_only_appear_when_the_range_reaches_today(fake_api, auth_env):
    fake_api.route(
        "gym-visit",
        visits_payload(
            [
                ("2026-09-10T02:16:19Z", "Example Club"),
            ]
        ),
    )
    result = visits.visits(now=NOW)
    assert result["daysSinceLastVisit"] == 8
    assert result["lastVisit"] == "2026-09-10 12:16"
    # The 90-day default window covers the last 7 days, so the counter is present.
    assert result["last7Days"] == 0
    assert result["last30Days"] == 1


def test_last7_and_last30_counts_within_a_wide_window(fake_api, auth_env):
    fake_api.route(
        "gym-visit",
        visits_payload(
            [
                ("2026-09-17T01:00:00Z", "Example Club"),
                ("2026-09-10T02:16:19Z", "Example Club"),
                ("2026-08-25T00:00:00Z", "Example Club"),
            ]
        ),
    )
    result = visits.visits(now=NOW)
    assert result["last7Days"] == 1
    assert result["last30Days"] == 3


def test_reversed_range_is_rejected():
    with pytest.raises(InvalidInputError, match="after"):
        visits.visits("2026-09-10", "2026-09-01", now=NOW)


def test_bad_dates_are_rejected():
    with pytest.raises(InvalidInputError):
        visits.visits("last tuesday", now=NOW)


def test_empty_default_window_widens_once(fake_api, auth_env):
    def handler(url: str, headers: dict, body: bytes | None):
        if "startDate=2024" in url:
            return visits_payload([("2025-03-18T00:31:16Z", "Example Club")])
        return []

    fake_api.route("gym-visit", handler)
    result = visits.visits(now=NOW)
    assert len(fake_api.calls) == 2  # narrow fetch, then widened fetch
    assert "note" in result
    assert result["totalInRange"] == 0
    assert result["lastVisit"] == "2025-03-18 11:31"  # DST-aware: March is AEDT


def test_most_common_day_and_hour_come_with_the_range(fake_api, auth_env):
    fake_api.route(
        "gym-visit",
        visits_payload(
            [
                ("2026-09-15T23:00:00Z", "Example Club"),  # Wed 09:00 local
                ("2026-09-08T23:00:00Z", "Example Club"),  # Wed 09:00 local
                ("2026-09-01T02:00:00Z", "Example Club"),  # Tue 12:00 local
            ]
        ),
    )
    result = visits.visits(now=NOW)
    assert result["totalInRange"] == 3
    assert result["mostCommonDay"] == {"day": "Wed", "visits": 2}
    assert result["mostCommonHour"] == {"hour": "09:00", "visits": 2}


def test_no_visits_reports_zero_and_no_habits(fake_api, auth_env):
    fake_api.route("gym-visit", [])
    result = visits.visits("2026-08-01", "2026-08-31", now=NOW)
    assert result["totalInRange"] == 0
    assert result["visits"] == []
    assert "mostCommonDay" not in result
    assert "mostCommonHour" not in result
