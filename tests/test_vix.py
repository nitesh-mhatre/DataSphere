"""Tests for the India VIX module."""

import pytest

import dataspear.nse.vix as vix_module
from dataspear.nse.vix import vix_regime
from dataspear.utils.yahoo import Candle


def _candles(closes):
    return [Candle(timestamp=i, open=c, high=c, low=c, close=c) for i, c in enumerate(closes)]


class TestVixRegime:
    def test_bands(self):
        assert vix_regime(10) == "LOW_FEAR"
        assert vix_regime(15) == "NORMAL"
        assert vix_regime(20) == "ELEVATED"
        assert vix_regime(30) == "EXTREME_FEAR"
        assert vix_regime(0) == "UNKNOWN"


class TestVixHistory:
    @pytest.mark.asyncio
    async def test_rising_trend_and_regime(self, monkeypatch):
        async def fake_candles(*_a, **_k):
            return _candles([12.0, 12.5, 13.0, 13.5, 14.0])

        monkeypatch.setattr(vix_module, "get_candles", fake_candles)
        data = await vix_module.get_india_vix_history(days=5)
        assert data["current"] == 14.0
        assert data["trend"] == "RISING"
        assert data["regime"] == "NORMAL"
        assert data["strategy_note"]

    @pytest.mark.asyncio
    async def test_insufficient_history(self, monkeypatch):
        async def fake_candles(*_a, **_k):
            return _candles([12.0])

        monkeypatch.setattr(vix_module, "get_candles", fake_candles)
        data = await vix_module.get_india_vix_history()
        assert data["current"] == 0.0
        assert data["regime"] == "UNKNOWN"
        assert "error" in data


class TestVixSpot:
    @pytest.mark.asyncio
    async def test_get_india_vix(self, monkeypatch):
        async def fake_quote(*_a, **_k):
            return {"price": 16.75}

        monkeypatch.setattr(vix_module, "get_quote", fake_quote)
        assert await vix_module.get_india_vix() == 16.75
