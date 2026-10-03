"""Shared India Standard Time (IST) helpers.

NSE operates on IST (UTC+05:30) and every NSE/Yahoo timestamp in dataspear is
interpreted in it, so the timezone plus the small conversion helpers live in one
place instead of being redefined in each module.

    from dataspear.utils.time import IST, now_ist, to_ist
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Current wall-clock time in IST."""
    return datetime.now(IST)


def today_ist() -> date:
    """Current IST calendar date."""
    return now_ist().date()


def to_ist(timestamp: float) -> datetime:
    """Convert an epoch (UTC seconds) ``timestamp`` into an IST datetime."""
    return datetime.fromtimestamp(timestamp, tz=IST)
