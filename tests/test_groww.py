"""Tests for the Groww data module (parsers, symbol builder, mocked fetches)."""

import json

import pytest

from dataspear import groww
from dataspear.groww import (
    build_groww_symbol,
    find_groww_contract,
    get_groww_option_chart,
    parse_candles,
    parse_chart,
    parse_next_data,
    parse_option_chain,
)


class TestBuildGrowwSymbol:
    """Groww contract-id construction (weekly vs monthly forms)."""

    def test_weekly_symbol(self):
        # 2026-10-06 -> YY=26, month letter O, day 06, strike 23000
        symbol = build_groww_symbol("NIFTY", "2026-10-06", 23000, "PE")
        assert symbol == "NIFTY26O0623000PE"

    def test_monthly_symbol(self):
        symbol = build_groww_symbol(
            "NIFTY", "2026-10-27", 23000, "CE", monthly=True
        )
        assert symbol == "NIFTY26OCT23000CE"

    def test_accepts_dd_mon_yyyy(self):
        assert (
            build_groww_symbol("nifty", "06-Oct-2026", 23000, "PE")
            == "NIFTY26O0623000PE"
        )

    def test_rejects_unknown_expiry(self):
        with pytest.raises(ValueError):
            build_groww_symbol("NIFTY", "not-a-date", 23000)


class TestParseCandles:
    """Groww's [ts, o, h, l, c, v] rows."""

    def test_parses_and_sorts(self):
        raw = {
            "candles": [
                [1790567400, 22951.7, 22951.8, 22914.45, 22926.5, None],
                [1790567100, 23064.9, 23079.75, 22946.95, 22949.5, 100],
            ]
        }
        candles = parse_candles(raw)
        assert [c.timestamp for c in candles] == [1790567100, 1790567400]
        assert candles[0].open == 23064.9
        assert candles[0].volume == 100
        assert candles[1].volume == 0  # None -> 0

    def test_skips_malformed_rows(self):
        raw = {"candles": [[1, 2, 3], ["x", 1, 2, 3, 4], None]}
        assert parse_candles(raw) == []

    def test_empty(self):
        assert parse_candles({}) == []
        assert parse_candles(None) == []


class TestParseChart:
    """Chart wrapper metadata + as_candles conversion."""

    def test_parse_chart(self):
        raw = {
            "candles": [[1790567100, 100, 110, 95, 105, 7]],
            "closingPrice": 12.5,
            "changeValue": 1.5,
            "changePerc": 13.6,
        }
        chart = parse_chart(raw, symbol="NIFTY26O0623000PE", segment="FNO")
        assert chart.symbol == "NIFTY26O0623000PE"
        assert chart.segment == "FNO"
        assert chart.last_price == 105
        assert chart.high == 110
        assert chart.low == 95
        assert chart.total_volume == 7
        assert chart.close_price == 12.5
        assert chart.to_dict()["change_pct"] == 13.6

    def test_as_candles_bridges_to_yahoo_candle(self):
        raw = {"candles": [[1790567100, 100, 110, 95, 105, 7]]}
        candle = parse_chart(raw).as_candles()[0]
        assert candle.close == 105
        assert candle.wick_up == 5  # 110 - max(100,105)
        assert candle.wick_down == 5  # min(100,105) - 95


SAMPLE_NEXT_DATA = {
    "props": {
        "pageProps": {
            "data": {
                "optionChain": {
                    "optionContracts": [
                        {
                            "strikePrice": 2005000,
                            "ce": {
                                "growwContractId": "NIFTY26O0620050CE",
                                "token": "40559",
                                "liveData": {
                                    "close": 4121.65,
                                    "ltp": 2388.2,
                                    "dayChange": -1733.45,
                                    "dayChangePerc": -42.05,
                                    "oi": 0,
                                    "prevOI": 0,
                                },
                                "greeks": {"delta": 0.9975, "iv": 34.86},
                                "markers": ["ILLIQUID"],
                            },
                            "pe": {
                                "growwContractId": "NIFTY26O0620050PE",
                                "token": "40560",
                                "liveData": {"ltp": 0.65, "close": 0.65, "oi": 825},
                            },
                        }
                    ],
                    "aggregatedDetails": {
                        "currentExpiry": "2026-10-06",
                        "expiryDates": ["2026-10-06", "2026-10-13"],
                        "lotSize": 65,
                        "freezeQty": 3511,
                    },
                },
                "company": {
                    "symbol": "NIFTY",
                    "liveData": {"ltp": 22421.95},
                },
            }
        }
    }
}


def _next_data_html(payload) -> str:
    return (
        "<html><head></head><body>"
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        "</body></html>"
    )


class TestParseNextData:
    def test_extracts_json(self):
        html = _next_data_html(SAMPLE_NEXT_DATA)
        assert parse_next_data(html)["props"]["pageProps"]

    def test_missing_returns_none(self):
        assert parse_next_data("<html></html>") is None

    def test_malformed_returns_none(self):
        html = '<script id="__NEXT_DATA__">{not json}</script>'
        assert parse_next_data(html) is None


class TestParseOptionChain:
    def test_parses_chain(self):
        chain = parse_option_chain(SAMPLE_NEXT_DATA, underlying="NIFTY")
        assert chain.underlying == "NIFTY"
        assert chain.spot == 22421.95
        assert chain.expiry == "2026-10-06"
        assert chain.expiries == ["2026-10-06", "2026-10-13"]
        assert chain.lot_size == 65
        assert chain.freeze_qty == 3511
        assert len(chain.strikes) == 1

        strike = chain.strikes[0]
        # 2005000 paise -> 20050.00
        assert strike.strike == 20050.0
        assert strike.ce.contract_id == "NIFTY26O0620050CE"
        assert strike.ce.ltp == 2388.2
        assert strike.ce.iv == 34.86
        assert strike.ce.markers == ["ILLIQUID"]
        assert strike.pe.oi == 825
        assert chain.atm_strike() == 20050.0

    def test_empty_payload(self):
        chain = parse_option_chain({}, underlying="NIFTY")
        assert chain.strikes == []
        assert chain.atm_strike() == 0.0


class TestFetchers:
    async def test_fetch_expiries(self, monkeypatch):
        async def fake_chain(underlying="NIFTY", expiry=None):
            return parse_option_chain(SAMPLE_NEXT_DATA, underlying=underlying)

        monkeypatch.setattr(groww, "fetch_groww_option_chain", fake_chain)
        assert await groww.fetch_groww_expiries("NIFTY") == [
            "2026-10-06",
            "2026-10-13",
        ]

    async def test_find_groww_contract(self, monkeypatch):
        async def fake_chain(underlying="NIFTY", expiry=None):
            return parse_option_chain(SAMPLE_NEXT_DATA, underlying=underlying)

        monkeypatch.setattr(groww, "fetch_groww_option_chain", fake_chain)
        symbol = await find_groww_contract("NIFTY", "2026-10-06", 20050, "PE")
        assert symbol == "NIFTY26O0620050PE"

    async def test_find_groww_contract_missing(self, monkeypatch):
        async def fake_chain(underlying="NIFTY", expiry=None):
            return parse_option_chain(SAMPLE_NEXT_DATA, underlying=underlying)

        monkeypatch.setattr(groww, "fetch_groww_option_chain", fake_chain)
        with pytest.raises(ValueError):
            await find_groww_contract("NIFTY", "2026-10-06", 99999, "CE")

    async def test_get_groww_option_chart_resolves_symbol(self, monkeypatch):
        async def fake_find(underlying, expiry, strike, option_type="CE"):
            return "NIFTY26O0620050PE"

        captured = {}

        async def fake_fetch(symbol, **kwargs):
            captured["symbol"] = symbol
            return parse_chart({"candles": []}, symbol=symbol, segment="FNO")

        monkeypatch.setattr(groww, "find_groww_contract", fake_find)
        monkeypatch.setattr(groww, "fetch_groww_option_chart", fake_fetch)

        chart = await get_groww_option_chart(
            "2026-10-06", 20050, "PE", fallback_nse=False
        )
        assert chart.symbol == "NIFTY26O0620050PE"
        assert captured["symbol"] == "NIFTY26O0620050PE"
        assert chart.source == "groww"

    async def test_get_groww_option_chart_falls_back_to_nse(self, monkeypatch):
        async def fake_find(underlying, expiry, strike, option_type="CE"):
            return "NIFTY26O0620050PE"

        async def fake_groww(symbol, **kwargs):
            return parse_chart({"candles": []}, symbol=symbol, segment="FNO")

        class _Point:
            def __init__(self, ts, price, volume):
                from datetime import datetime

                self.timestamp = datetime.fromtimestamp(ts)
                self.price = price
                self.volume = volume

        class _NseChart:
            close_price = 100.0
            points = [_Point(1, 101.0, 5), _Point(2, 102.0, 7)]

        async def fake_nse(expiry, strike, option_type="CE"):
            return _NseChart()

        import dataspear.nse.option_chart as nse_oc

        monkeypatch.setattr(groww, "find_groww_contract", fake_find)
        monkeypatch.setattr(groww, "fetch_groww_option_chart", fake_groww)
        monkeypatch.setattr(nse_oc, "fetch_option_chart", fake_nse)

        chart = await get_groww_option_chart("2026-10-06", 20050, "PE")
        assert chart.source == "nse"
        assert len(chart.candles) == 2
        assert chart.last_price == 102.0
        assert chart.total_volume == 12
