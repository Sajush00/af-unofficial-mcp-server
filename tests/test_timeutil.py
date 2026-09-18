"""Tests for the time seam: club-local parsing, DST awareness, conversions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from af_mcp import timeutil
from af_mcp.errors import InvalidInputError
from factories import home_gym


def test_club_zone_is_resolved_from_home_gym_coordinates(
    fake_api, auth_env, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("AF_CLUB_TZ")
    timeutil.club_zone.cache_clear()
    fake_api.route("me/user/my-gym", home_gym())

    assert str(timeutil.club_zone()) == "Australia/Sydney"
    assert len(fake_api.calls) == 1


def test_bad_timezone_override_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AF_CLUB_TZ", "Not/A-Timezone")
    timeutil.club_zone.cache_clear()
    with pytest.raises(InvalidInputError, match="AF_CLUB_TZ"):
        timeutil.club_zone()


def test_bare_date_start_snaps_to_midnight_club_time():
    bound = timeutil.parse_bound("2026-08-01", end_of_day=False)
    assert (bound.hour, bound.minute, bound.second) == (0, 0, 0)
    assert bound.tzinfo is not None
    assert bound.utcoffset() == timedelta(hours=10)  # August is AEST


def test_bare_date_end_covers_the_whole_day():
    bound = timeutil.parse_bound("2026-08-01", end_of_day=True)
    assert (bound.hour, bound.minute, bound.second) == (23, 59, 59)


def test_summer_bounds_use_the_daylight_offset():
    """The old code hardcoded +10 and was an hour wrong every summer."""
    january = timeutil.parse_bound("2026-01-15T12:00", end_of_day=False)
    assert january.utcoffset() == timedelta(hours=11)


def test_iso_datetimes_are_honoured_as_given():
    bound = timeutil.parse_bound("2026-08-01T09:30", end_of_day=True)
    assert (bound.hour, bound.minute, bound.second) == (9, 30, 0)


def test_utc_suffix_is_respected():
    bound = timeutil.parse_bound("2026-08-01T09:30Z", end_of_day=False)
    assert bound.utcoffset() == timedelta(0)


def test_bad_date_raises_bad_input():
    with pytest.raises(InvalidInputError):
        timeutil.parse_bound("next tuesday", end_of_day=False)


def test_to_utc_formats_the_wire_shape():
    moment = timeutil.parse_bound("2026-08-01T09:30", end_of_day=False)
    assert timeutil.to_utc(moment) == "2026-07-31T23:30:00Z"


def test_days_ago_counts_calendar_days():
    visit = timeutil.parse_bound("2026-09-10T23:50", end_of_day=False)
    reference = timeutil.parse_bound("2026-09-12T00:10", end_of_day=False)
    assert timeutil.days_ago(visit, reference=reference) == 2


def test_days_ago_can_be_zero_for_today():
    visit = timeutil.parse_bound("2026-09-12T06:00", end_of_day=False)
    reference = timeutil.parse_bound("2026-09-12T22:00", end_of_day=False)
    assert timeutil.days_ago(visit, reference=reference) == 0


def test_local_and_formatting_helpers_agree():
    moment = timeutil.parse_bound("2026-08-01T09:30Z", end_of_day=False)
    assert timeutil.date_string(moment) == "2026-08-01"
    assert timeutil.moment_string(moment) == "2026-08-01 19:30"
    assert isinstance(timeutil.local(moment), datetime)
