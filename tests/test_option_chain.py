"""Tests for NSE option chain parsing and OI analysis."""

from dataspear.nse.analysis import (
    iv_skew,
    max_pain,
    oi_analysis,
    oi_buildup_unwinding,
    pcr_sentiment,
    support_resistance,
    top_oi_strikes,
)
from dataspear.nse.option_chain import parse_option_chain
from dataspear.nse.models import OptionChain


def _quote(oi, chg, vol, iv, ltp):
    return {
        "openInterest": oi,
        "changeinOpenInterest": chg,
        "totalTradedVolume": vol,
        "impliedVolatility": iv,
        "lastPrice": ltp,
        "change": 1.5,
        "buyPrice1": ltp - 0.5,
        "sellPrice1": ltp + 0.5,
    }


SAMPLE = {
    "records": {
        "underlyingValue": 24230.0,
        "data": [
            {"strikePrice": 24000, "expiryDate": "05-May-2026",
             "CE": _quote(100000, 5000, 20000, 12.0, 300.0),
             "PE": _quote(150000, -3000, 25000, 13.0, 80.0)},
            {"strikePrice": 24100, "expiryDate": "05-May-2026",
             "CE": _quote(120000, 8000, 18000, 13.0, 220.0),
             "PE": _quote(130000, 4000, 22000, 12.5, 110.0)},
            {"strikePrice": 24200, "expiryDate": "05-May-2026",
             "CE": _quote(180000, 20000, 30000, 11.5, 150.0),
             "PE": _quote(90000, -5000, 28000, 12.0, 145.0)},
            {"strikePrice": 24300, "expiryDate": "05-May-2026",
             "CE": _quote(200000, 10000, 26000, 12.5, 95.0),
             "PE": _quote(60000, 2000, 15000, 13.5, 210.0)},
            {"strikePrice": 24400, "expiryDate": "05-May-2026",
             "CE": _quote(90000, -2000, 12000, 14.0, 60.0),
             "PE": _quote(40000, 1000, 8000, 15.0, 300.0)},
        ],
    }
}


class TestParse:
    def test_parse_basic(self):
        chain = parse_option_chain(SAMPLE)
        assert chain.spot == 24230.0
        assert chain.expiry == "05-May-2026"
        assert len(chain.strikes) == 5
        assert [s.strike for s in chain.strikes] == [24000, 24100, 24200, 24300, 24400]

    def test_quotes_parsed(self):
        chain = parse_option_chain(SAMPLE)
        atm = next(s for s in chain.strikes if s.strike == 24200)
        assert atm.ce.oi == 180000
        assert atm.ce.change_oi == 20000
        assert atm.pe.oi == 90000
        assert atm.pe.iv == 12.0
        assert atm.ce.bid == 149.5

    def test_handles_missing_side(self):
        data = {"records": {"underlyingValue": 100.0, "data": [
            {"strikePrice": 100, "CE": {"openInterest": 5}},
            {"strikePrice": 110},
        ]}}
        chain = parse_option_chain(data)
        assert len(chain.strikes) == 2
        assert chain.strikes[1].pe.oi == 0

    def test_handles_empty(self):
        chain = parse_option_chain({})
        assert chain.strikes == []
        assert chain.pcr == 0.0
        assert chain.atm_strike() is None


class TestAggregates:
    def test_pcr(self):
        chain = parse_option_chain(SAMPLE)
        # PE total 470000 / CE total 690000
        assert chain.pcr == 0.68

    def test_atm_strike(self):
        chain = parse_option_chain(SAMPLE)
        assert chain.atm_strike() == 24200

    def test_filter_atm(self):
        chain = parse_option_chain(SAMPLE)
        filtered = chain.filter_atm(1)
        assert [s.strike for s in filtered.strikes] == [24100, 24200, 24300]

    def test_filter_atm_keeps_totals_consistent(self):
        chain = parse_option_chain(SAMPLE).filter_atm(1)
        assert chain.ce_oi_total == 120000 + 180000 + 200000


class TestAnalysis:
    def test_pcr_sentiment_bands(self):
        assert "BULLISH" in pcr_sentiment(1.4)
        assert "NEUTRAL-BULLISH" in pcr_sentiment(1.0)
        assert "NEUTRAL-BEARISH" in pcr_sentiment(0.8)
        assert "BEARISH" in pcr_sentiment(0.5)

    def test_max_pain_is_a_strike(self):
        chain = parse_option_chain(SAMPLE)
        assert max_pain(chain) in chain.strike_prices

    def test_top_oi_strikes(self):
        chain = parse_option_chain(SAMPLE)
        assert top_oi_strikes(chain, "CE", 1)[0].strike == 24300
        assert top_oi_strikes(chain, "PE", 1)[0].strike == 24000

    def test_support_resistance(self):
        chain = parse_option_chain(SAMPLE)
        sr = support_resistance(chain)
        assert sr["key_resistance"][0]["strike"] == 24300
        assert sr["key_support"][0]["strike"] == 24000

    def test_buildup_unwinding(self):
        chain = parse_option_chain(SAMPLE)
        changes = oi_buildup_unwinding(chain)
        assert changes["fresh_ce_writing"][0]["strike"] == 24200
        assert changes["fresh_ce_writing"][0]["change_oi"] > 0
        assert all(r["change_oi"] < 0 for r in changes["ce_unwinding"])

    def test_iv_skew_centered_on_atm(self):
        chain = parse_option_chain(SAMPLE)
        skew = iv_skew(chain, span=1)
        assert [r["strike"] for r in skew] == [24100, 24200, 24300]

    def test_oi_analysis_shape(self):
        summary = oi_analysis(parse_option_chain(SAMPLE))
        for key in ("pcr", "sentiment", "max_pain", "key_resistance",
                    "key_support", "fresh_ce_writing", "iv_skew"):
            assert key in summary


class TestSerialization:
    def test_to_dict_round_trips(self):
        chain = parse_option_chain(SAMPLE)
        d = chain.to_dict()
        assert d["atm_strike"] == 24200
        assert len(d["strikes"]) == 5
        assert d["strikes"][0]["strike"] == 24000.0


class TestOptionChainFromPlain:
    def test_construct_without_spot(self):
        chain = OptionChain(spot=0.0, strikes=parse_option_chain(SAMPLE).strikes)
        assert chain.atm_strike() == 24200  # median fallback
