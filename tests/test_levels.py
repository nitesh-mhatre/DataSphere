"""Tests for the pure level-detection helpers."""

from dataspear.nse.levels import (
    detect_levels,
    distribution_accumulation_zones,
    opening_fake_frequency,
    swing_highs,
    swing_lows,
    wick_levels,
)
from dataspear.utils.yahoo import Candle


def C(ts, o, h, l, c, v=0):
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


def _series(highs):
    return [
        C(i, h - 0.5, h, h - 1.0, h - 0.5)
        for i, h in enumerate(highs)
    ]


class TestSwings:
    def test_swing_high_pivot(self):
        candles = _series([1, 2, 3, 4, 5, 4, 3, 2, 1])
        assert swing_highs(candles, n=2) == [5.0]

    def test_swing_low_pivot(self):
        candles = _series([5, 4, 3, 2, 1, 2, 3, 4, 5])
        # lows are (high - 1), so the pivot high of 1 has a low of 0.
        assert swing_lows(candles, n=2) == [0.0]


class TestWickLevels:
    def test_requires_min_hits(self):
        candles = [
            C(1, 120, 160, 119, 120),  # upper wick 40 -> level 150
            C(2, 120, 162, 119, 121),  # upper wick 41 -> level 150
            C(3, 300, 330, 299, 300),  # single hit at 350 -> ignored
        ]
        assert wick_levels(candles, threshold_wick=25, min_hits=2) == [150.0]

    def test_lower_wicks(self):
        candles = [
            C(1, 180, 181, 140, 180),  # lower wick 40 -> round(140)=150
            C(2, 180, 181, 138, 179),  # lower wick 41 -> round(138)=150
        ]
        assert wick_levels(candles, threshold_wick=25, min_hits=2) == [150.0]


class TestZones:
    def test_distribution_and_accumulation(self):
        candles = [
            C(1, 100, 101, 100, 100.5, v=10),
            C(2, 100, 130, 99, 101, v=100),  # high vol upper wick -> distribution
            C(3, 100, 101, 70, 99, v=100),   # high vol lower wick -> accumulation
        ]
        zones = distribution_accumulation_zones(candles, vol_mult=1.2)
        assert zones["distribution"] == [150.0]
        assert zones["accumulation"] == [50.0]


class TestOpeningFake:
    def test_counts_small_body_days(self):
        candles = [
            C(1, 100, 120, 80, 101),  # body 1 / range 40 -> fake
            C(2, 100, 101, 99, 100.2),  # body 0.2 / range 2 -> fake
            C(3, 100, 130, 100, 130),  # full body -> not fake
        ]
        assert opening_fake_frequency(candles, lookback=3) == 2


class TestDetectLevels:
    def test_smoke(self):
        daily = _series([100, 101, 102, 103, 104, 103, 102, 101, 100])
        result = detect_levels([daily, daily])
        assert result.summary
        assert isinstance(result.to_dict(), dict)
        assert "swing_highs" in result.to_dict()

    def test_no_candles(self):
        result = detect_levels([[]])
        assert result.summary == "No candles supplied."
