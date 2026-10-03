"""Tests for the full-market context aggregator."""

import pytest

import dataspear.nse.context as context
from dataspear.nse.context import MarketContext, build_market_context
from dataspear.nse.scanner import MarketBrief
from dataspear.news import NewsArticle


def _article(title):
    return NewsArticle(
        title=title,
        source="Test Wire",
        published="2026-05-04",
        url="https://example.com",
        category="market",
    )


def _brief():
    return MarketBrief(
        fetched_at="10:00:00",
        expiry="05-May-2026",
        spot=24230.0,
        atm=24250,
        pcr=0.92,
        sentiment="MILDLY_BEARISH",
        max_pain=24250,
        vix=14.5,
    )


def _patch_sections(monkeypatch, news=None, global_raises=False):
    async def fake_brief(expiry=None, direction="BOTH", fetch_charts=True):
        return _brief()

    async def fake_tech():
        return {"trend": "SIDEWAYS", "ltp": 24230.0}

    async def fake_global():
        if global_raises:
            raise RuntimeError("yahoo down")
        return {"global_bias": "MIXED"}

    async def fake_fii():
        return {"market_signal": "BULLISH"}

    async def fake_premarket():
        return {"gap_direction": "GAP_UP"}

    async def fake_news(days=1):
        return news or []

    monkeypatch.setattr(context, "build_market_brief", fake_brief)
    monkeypatch.setattr(context, "get_nifty_technicals", fake_tech)
    monkeypatch.setattr(context, "get_global_indices", fake_global)
    monkeypatch.setattr(context, "get_fii_dii_data", fake_fii)
    monkeypatch.setattr(context, "get_premarket_data", fake_premarket)
    monkeypatch.setattr(context, "fetch_all_news", fake_news)


class TestBuildMarketContext:
    @pytest.mark.asyncio
    async def test_gathers_all_sections(self, monkeypatch):
        _patch_sections(monkeypatch, news=[_article("a"), _article("b")])

        ctx = await build_market_context(expiry="05-May-2026")
        assert isinstance(ctx, MarketContext)
        assert ctx.brief.expiry == "05-May-2026"
        assert ctx.technicals["trend"] == "SIDEWAYS"
        assert ctx.global_indices["global_bias"] == "MIXED"
        assert ctx.fii_dii["market_signal"] == "BULLISH"
        assert ctx.premarket["gap_direction"] == "GAP_UP"
        assert [a.title for a in ctx.news] == ["a", "b"]
        assert ctx.market_status.phase in ("NORMAL", "PRE_OPEN", "CLOSING", "CLOSED")
        assert isinstance(ctx.to_dict()["brief"], dict)
        assert ctx.to_dict()["news"][0]["title"] == "a"

    @pytest.mark.asyncio
    async def test_news_can_be_skipped(self, monkeypatch):
        _patch_sections(monkeypatch, news=["ignored"])

        ctx = await build_market_context(include_news=False)
        assert ctx.news == []

    @pytest.mark.asyncio
    async def test_section_failure_degrades(self, monkeypatch):
        _patch_sections(monkeypatch, global_raises=True)

        ctx = await build_market_context(include_news=False)
        assert ctx.global_indices == {}
        # The brief still comes through.
        assert ctx.brief.spot == 24230.0
