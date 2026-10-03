"""Tests for market extras (FII/DII signals, technicals, pre-market)."""

from datetime import datetime, timedelta, timezone

from dataspear.nse.market_extra import (
    _compute_technicals,
    _fii_signal,
    _global_bias,
    _premarket_from_quote,
)
from dataspear.utils.yahoo import Candle

IST = timezone(timedelta(hours=5, minutes=30))


def _candles(closes, volumes=None):
    now = datetime.now(IST).timestamp()
    volumes = volumes or [100] * len(closes)
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        out.append(
            Candle(
                timestamp=int(now) - (len(closes) - i) * 300,
                open=c - 1,
                high=c + 1,
                low=c - 2,
                close=c,
                volume=v,
            )
        )
    return out


class TestFiiSignal:
    def test_bands(self):
        assert _fii_signal(800) == "STRONG_BUYING"
        assert _fii_signal(100) == "BUYING"
        assert _fii_signal(-100) == "SELLING"
        assert _fii_signal(-900) == "HEAVY_SELLING"


class TestGlobalBias:
    def test_bullish(self):
        result = {k: {"change_pct": 1.0} for k in ("sp500", "nasdaq", "nikkei", "hangseng")}
        assert _global_bias(result) == "BULLISH"

    def test_mixed(self):
        assert _global_bias({}) == "MIXED"


class TestTechnicals:
    def test_uptrend(self):
        tech = _compute_technicals(_candles(list(range(100, 140))))
        assert tech["trend"] in ("UPTREND", "STRONG_UPTREND")
        assert tech["tech_bias"] == "BULLISH"
        assert tech["vwap"] > 0

    def test_empty(self):
        assert _compute_technicals([]) == {}

    def test_vwap_weighted(self):
        closes = [100, 100, 100, 200]
        vols = [10, 10, 10, 10]
        tech = _compute_technicals(_candles(closes, vols))
        # Typical prices are close-1, so VWAP is pulled up by the last candle.
        assert tech["vwap"] > 120


class TestPremarket:
    def test_gap_up(self):
        data = _premarket_from_quote({"price": 24250.0, "prev_close": 24000.0})
        assert data["gap_direction"] == "GAP_UP"
        assert data["gap_points"] == 250.0
        assert "GAP_UP" in data["trade_note"]

    def test_flat(self):
        data = _premarket_from_quote({"price": 24000.0, "prev_close": 24000.0})
        assert data["gap_direction"] == "FLAT"

    def test_unavailable(self):
        assert "error" in _premarket_from_quote({"price": 0.0, "prev_close": 0.0})
