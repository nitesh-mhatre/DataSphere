"""Tests for the shared IST time helpers."""

from datetime import datetime, timedelta, timezone

from dataspear.utils.time import IST, now_ist, to_ist, today_ist


def test_ist_offset():
    assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)


def test_now_ist_is_aware_and_ist():
    now = now_ist()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(hours=5, minutes=30)


def test_today_ist_matches_now():
    assert today_ist() == now_ist().date()


def test_to_ist_converts_utc_epoch():
    dt = to_ist(0.0)
    assert dt == datetime(1970, 1, 1, 5, 30, tzinfo=IST)


def test_to_ist_roundtrip_with_utcnow():
    epoch = datetime.now(timezone.utc).timestamp()
    assert abs((to_ist(epoch) - now_ist()).total_seconds()) < 5
