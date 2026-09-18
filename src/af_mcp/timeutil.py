"""Club-local time handling: the package's single time seam.

The AF API reports UTC timestamps (Z suffixed) and club-local wall-clock
values (busy-meter hours). Every conversion lives here so the club timezone
is defined once. Fixed UTC offsets are banned (static check AF002): Sydney is
UTC+11 in summer and UTC+10 in winter, so a hardcoded offset is wrong half
the year.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from af_mcp.errors import InvalidInputError

DEFAULT_CLUB_TIMEZONE = "Australia/Sydney"


def club_zone() -> ZoneInfo:
    """The home club's timezone (AF_CLUB_TZ overrides the default)."""
    return ZoneInfo(os.environ.get("AF_CLUB_TZ", DEFAULT_CLUB_TIMEZONE))


def now() -> datetime:
    """Current time as an aware datetime in the club timezone."""
    return datetime.now(club_zone())


def parse_utc(timestamp: str) -> datetime:
    """Parse an API timestamp (UTC, Z suffixed) into an aware datetime."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def parse_bound(value: str, *, end_of_day: bool) -> datetime:
    """Parse a range bound as club-local time.

    A bare date (2026-08-01) covers the whole local day: it snaps to
    00:00:00 for a start bound and 23:59:59 for an end bound. ISO datetimes
    are honoured as given and gain the club timezone when naive.
    """
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidInputError(
            f"Bad date {value!r}: use YYYY-MM-DD or an ISO datetime like 2026-09-01T18:00."
        ) from exc
    if parsed.tzinfo is None:
        if len(text) <= 10 and end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        parsed = parsed.replace(tzinfo=club_zone())
    return parsed


def to_utc(moment: datetime) -> str:
    """Format an aware datetime as the API's UTC wire format."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def local(moment: datetime) -> datetime:
    """Convert an aware datetime to the club timezone."""
    return moment.astimezone(club_zone())


def date_string(moment: datetime) -> str:
    """Club-local calendar date as YYYY-MM-DD."""
    return local(moment).strftime("%Y-%m-%d")


def moment_string(moment: datetime) -> str:
    """Club-local date and time as YYYY-MM-DD HH:MM."""
    return local(moment).strftime("%Y-%m-%d %H:%M")


def days_ago(moment: datetime, *, reference: datetime | None = None) -> int:
    """Whole club-local calendar days between a past moment and the reference."""
    anchor = local(reference or now()).date()
    return (anchor - local(moment).date()).days
