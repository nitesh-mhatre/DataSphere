"""Tests for the MarketBrief scanner."""

import pytest

import dataspear.nse.scanner as scanner
from dataspear.nse.models import OptionChain, OptionQuote, OptionStrike
from dataspear.nse.scanner import (
    MarketBrief,
    build_market_brief,
    select_target_strikes,
)


def _chain():
    strikes = []
    for s in range(23900, 24600, 50):
        strikes.append(
            OptionStrike(
                strike=float(s),
                expiry="05-May-2026",
                ce=OptionQuote(oi=100000 + abs(24250 - s) * 100, ltp=100.0),
                pe=OptionQuote(oi=90000 + abs(24250 - s) * 100, ltp=90.0),
            )
        )
    return OptionChain(symbol="NIFTY", spot=24230.0, expiry="05-May-2026", strikes=strikes)


class TestSelectTargetStrikes:
    def test_sideways_fetches_both_sides(self):
        targets = select_target_strikes(_chain(), "MILDLY_BULLISH")
        assert (24300, "CE") in targets
        assert (24200, "PE") in targets

    def test_bullish_atm_ce(self):
        targets = select_target_strikes(_chain(), "BULLISH", direction="BOTH")
        assert targets[0] == (24250, "CE")

    def test_empty_chain(self):
        assert select_target_strikes(OptionChain(), "BULLISH") == []


class TestBuildMarketBrief:
    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        async def fake_chain(expiry=None, atm_range=None):
            return _chain()

        async def fake_vix():
            return 14.5

        monkeypatch.setattr(scanner, "get_nifty_option_chain", fake_chain)
        monkeypatch.setattr(scanner, "get_india_vix", fake_vix)

        brief = await build_market_brief(expiry="05-May-2026", fetch_charts=False)
        assert isinstance(brief, MarketBrief)
        assert brief.expiry == "05-May-2026"
        assert brief.atm == 24250
        assert brief.vix == 14.5
        assert brief.pcr > 0
        assert brief.resistance
        assert brief.error is None
        # Enriched fields (all computed from pure helpers, no extra I/O).
        assert brief.vix_regime == "NORMAL"
        assert brief.regime == "SIDEWAYS"
        assert brief.strategy
        assert brief.market_phase in ("NORMAL", "PRE_OPEN", "CLOSING", "CLOSED")
        assert isinstance(brief.market_open, bool)
        assert brief.to_dict()["regime"] == "SIDEWAYS"

    @pytest.mark.asyncio
    async def test_error_is_captured(self, monkeypatch):
        async def boom(expiry=None, atm_range=None):
            raise RuntimeError("NSE down")

        monkeypatch.setattr(scanner, "get_nifty_option_chain", boom)

        brief = await build_market_brief(expiry="05-May-2026", fetch_charts=False)
        assert brief.error == "NSE down"
        assert brief.sentiment == "UNKNOWN"
        assert brief.to_dict()["error"] == "NSE down"
