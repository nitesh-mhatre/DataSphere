"""Tests for the market regime classifier."""

from dataspear.nse.regime import classify_pcr, detect_regime


class TestClassifyPcr:
    def test_bands(self):
        assert classify_pcr(1.6) == "STRONGLY_BULLISH"
        assert classify_pcr(1.3) == "BULLISH"
        assert classify_pcr(1.05) == "MILDLY_BULLISH"
        assert classify_pcr(0.9) == "MILDLY_BEARISH"
        assert classify_pcr(0.7) == "BEARISH"
        assert classify_pcr(0.5) == "STRONGLY_BEARISH"


class TestDetectRegime:
    def test_sideways(self):
        regime = detect_regime(
            pcr=1.0,
            vix=12.0,
            tech={"trend": "SIDEWAYS", "ema9": 24000, "ema21": 24000, "vwap": 24000},
            spot=24000,
            ce_wall=24050,
            pe_wall=23950,
        )
        assert regime.regime == "SIDEWAYS"
        assert regime.strategy.startswith("SHORT_")
        assert regime.is_sideways

    def test_volatile(self):
        regime = detect_regime(pcr=1.0, vix=30.0, spot=24000)
        assert regime.regime == "VOLATILE"
        assert regime.is_volatile

    def test_strongly_directional_bullish(self):
        regime = detect_regime(
            pcr=1.6,
            vix=20.0,
            tech={"trend": "STRONG_UPTREND", "ema9": 24100, "ema21": 24000, "vwap": 24050},
            spot=24150,
            ce_wall=24800,
            pe_wall=24200,
        )
        assert regime.regime == "STRONGLY_DIRECTIONAL"
        assert regime.direction == "BULLISH"
        assert regime.confidence >= 4

    def test_unclear_has_no_trade_reason(self):
        regime = detect_regime(pcr=1.0, vix=17.0, spot=24000)
        # No walls supplied -> default tight range, but no tech signal.
        assert regime.prompt_block()
        assert isinstance(regime.to_dict(), dict)
