"""Tests for occupancy (live count + verdict), forecast, and nearby clubs."""

from __future__ import annotations

import pytest

from af_mcp import occupancy, timeutil
from af_mcp.errors import InvalidInputError
from factories import busy_batch, busy_meter, search_results, week
from factories import home_gym as home_gym_payload

WEDNESDAY_11 = timeutil.parse_bound("2026-09-16T11:30", end_of_day=False)  # Wed, mid-morning


def test_occupancy_reports_live_count_verdict_and_rest_of_day(fake_api, auth_env):
    fake_api.route("my-gym", home_gym_payload())
    fake_api.route(
        "busy-meter",
        busy_meter(
            current=24,
            peak=48,
            days=week({"Wednesday": [("09:00", 10), ("11:00", 30), ("18:00", 44), ("22:00", 12)]}),
        ),
    )
    result = occupancy.occupancy(now=WEDNESDAY_11)
    assert result["afNumber"] == "AU-0000"
    assert result["currentMemberCount"] == 24
    assert result["typicalCount"] == 30
    assert result["ratio"] == 0.8
    assert result["verdict"] == "good-time"
    assert result["verdictMessage"]
    # 09:00 is in the past for an 11:30 "now"; only later hours remain.
    assert [row["hour"] for row in result["restOfDay"]] == ["11:00", "18:00", "22:00"]


def test_occupancy_without_live_count(fake_api, auth_env):
    fake_api.route("busy-meter", busy_meter(current=None, peak=None, days=[]))
    result = occupancy.occupancy("AU-9999", now=WEDNESDAY_11)
    assert result["currentMemberCount"] is None
    assert result["verdict"] == "no-live-data"
    assert result["ratio"] is None
    assert result["restOfDay"] == []


@pytest.mark.parametrize(
    ("current", "typical", "verdict"),
    [
        (10, 40, "go-now"),  # ratio 0.25
        (30, 40, "good-time"),  # 0.75
        (44, 40, "normal"),  # 1.10
        (56, 40, "wait"),  # 1.40
        (80, 40, "skip"),  # 2.00
    ],
)
def test_verdict_bands_follow_the_live_to_typical_ratio(
    fake_api, auth_env, current, typical, verdict
):
    fake_api.route("my-gym", home_gym_payload())
    fake_api.route(
        "busy-meter",
        busy_meter(current=current, days=week({"Wednesday": [("11:00", typical)]})),
    )
    result = occupancy.occupancy(now=WEDNESDAY_11)
    assert result["verdict"] == verdict
    assert result["typicalCount"] == typical
    assert result["ratio"] == pytest.approx(current / typical, abs=0.01)


def test_verdict_without_baseline_for_this_hour(fake_api, auth_env):
    fake_api.route("my-gym", home_gym_payload())
    fake_api.route(
        "busy-meter",
        busy_meter(
            current=30,
            days=week({"Wednesday": [("06:00", 10)]}),
        ),
    )
    result = occupancy.occupancy(now=WEDNESDAY_11)
    assert result["verdict"] == "no-baseline"
    assert result["verdictMessage"]
    assert result["currentMemberCount"] == 30
    assert result["typicalCount"] is None


def test_forecast_resolves_relative_and_named_days(fake_api, auth_env):
    fake_api.route("my-gym", home_gym_payload())
    fake_api.route(
        "busy-meter",
        busy_meter(
            days=week({"Friday": [("06:00", 12)], "Monday": [("06:00", 30)]}),
        ),
    )
    friday = occupancy.forecast("friday", now=WEDNESDAY_11)
    assert friday["date"] == "2026-09-18"
    assert friday["weekday"] == "Friday"
    assert friday["hours"] == [{"hour": "06:00", "typicalCount": 12}]
    monday = occupancy.forecast("Monday", now=WEDNESDAY_11)
    assert monday["date"] == "2026-09-21"  # next Monday, not today


def test_forecast_today_and_tomorrow(fake_api, auth_env):
    fake_api.route("my-gym", home_gym_payload())
    fake_api.route("busy-meter", busy_meter(days=[]))
    assert occupancy.forecast("today", now=WEDNESDAY_11)["date"] == "2026-09-16"
    assert occupancy.forecast("tomorrow", now=WEDNESDAY_11)["date"] == "2026-09-17"


def test_forecast_rejects_unknown_day(fake_api, auth_env):
    fake_api.route("my-gym", home_gym_payload())
    fake_api.route("busy-meter", busy_meter(days=[]))
    with pytest.raises(InvalidInputError, match="Unknown day"):
        occupancy.forecast("blursday", now=WEDNESDAY_11)


def test_nearby_clubs_merges_live_counts(fake_api, auth_env):
    from af_mcp.clubs import nearby

    numbers = ["AU-1", "AU-2"]
    fake_api.route("my-gym", home_gym_payload(af_number="AU-1", name="Home"))
    fake_api.route("location/search", search_results(numbers=numbers))
    fake_api.route("clubs/busy-meter", busy_batch(numbers=numbers))
    gym, clubs = nearby(radius_km=10, limit=2)
    assert gym["afNumber"] == "AU-1"
    assert [club["afNumber"] for club in clubs] == numbers
    assert [club["currentMemberCount"] for club in clubs] == [5, 6]
    assert clubs[0]["isHomeGym"] is True
    assert clubs[1]["isHomeGym"] is False
    assert clubs[0]["distanceKm"] == 1.5


def test_nearby_clubs_survives_batch_failure(fake_api, auth_env):
    from af_mcp.clubs import nearby
    from af_mcp.errors import TransportError

    fake_api.route("my-gym", home_gym_payload())
    fake_api.route("location/search", search_results(numbers=["AU-1"]))
    fake_api.route("clubs/busy-meter", TransportError("boom"))
    _, clubs = nearby(radius_km=10, limit=1)
    assert clubs[0]["currentMemberCount"] is None
