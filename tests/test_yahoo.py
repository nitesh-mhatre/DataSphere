"""Tests for the Yahoo chart client helpers."""

from dataspear.utils.yahoo import Candle, parse_chart, quote_from_meta

PAYLOAD = {
    "chart": {
        "result": [
            {
                "meta": {"regularMarketPrice": 100.5, "chartPreviousClose": 99.0},
                "timestamp": [1, 2, 3],
                "indicators": {
                    "quote": [
                        {
                            "open": [99, 100, 101],
                            "high": [101, 102, 103],
                            "low": [98, 99, 100],
                            "close": [100, 101, None],
                            "volume": [10, 20, 30],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}


class TestParseChart:
    def test_parses_candles_and_skips_null_close(self):
        meta, candles = parse_chart(PAYLOAD)
        assert meta["regularMarketPrice"] == 100.5
        assert len(candles) == 2
        assert candles[0].close == 100
        assert candles[1].volume == 20

    def test_empty_payload(self):
        meta, candles = parse_chart({})
        assert meta == {}
        assert candles == []

    def test_empty_result(self):
        meta, candles = parse_chart({"chart": {"result": []}})
        assert meta == {}
        assert candles == []


class TestQuoteFromMeta:
    def test_change_and_pct(self):
        q = quote_from_meta({"regularMarketPrice": 100.5, "chartPreviousClose": 99.0})
        assert q["price"] == 100.5
        assert q["prev_close"] == 99.0
        assert q["change"] == 1.5
        assert q["change_pct"] == 1.52

    def test_falls_back_to_price_when_prev_missing(self):
        q = quote_from_meta({"regularMarketPrice": 50.0})
        assert q["change"] == 0.0
        assert q["change_pct"] == 0.0


class TestCandleProperties:
    def test_wicks_and_body(self):
        c = Candle(timestamp=0, open=100, high=115, low=95, close=110, volume=5)
        assert c.body == 10
        assert c.wick_up == 5
        assert c.wick_down == 5
        assert c.total_range == 20
        assert c.is_bullish is True
