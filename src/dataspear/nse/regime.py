"""Market regime classifier.

Combines four independent, cheap signals to classify the tape:

1. PCR band              - range-bound vs directional
2. OI wall tightness     - CE/PE walls close together = range
3. VIX level             - calm vs volatile
4. Intraday technicals   - trend, or EMA9/EMA21 hugging VWAP

Outputs one of: ``SIDEWAYS``, ``MILDLY_DIRECTIONAL``, ``STRONGLY_DIRECTIONAL``,
``VOLATILE``, ``UNCLEAR`` plus a suggested strategy. Pure logic - feed it data
from the option chain, :mod:`dataspear.nse.vix` and
:func:`dataspear.nse.market_extra.get_nifty_technicals`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


def classify_pcr(pcr: float) -> str:
    """Granular PCR -> sentiment band (avoids a wide NEUTRAL dead zone)."""
    if pcr >= 1.50:
        return "STRONGLY_BULLISH"
    if pcr >= 1.20:
        return "BULLISH"
    if pcr >= 1.00:
        return "MILDLY_BULLISH"
    if pcr >= 0.85:
        return "MILDLY_BEARISH"
    if pcr >= 0.65:
        return "BEARISH"
    return "STRONGLY_BEARISH"


_TIGHT_RANGE_PTS = 250
_MODERATE_RANGE_PTS = 400


@dataclass
class MarketRegime:
    regime: str
    confidence: int
    direction: str  # BULLISH | BEARISH | NEUTRAL
    range_low: float
    range_high: float
    range_width_pts: float
    vix: float
    pcr: float
    tech_trend: str
    signals: List[str] = field(default_factory=list)
    strategy: str = ""
    strategy_detail: str = ""
    no_trade_reason: str = ""

    @property
    def is_sideways(self) -> bool:
        return self.regime == "SIDEWAYS"

    @property
    def is_directional(self) -> bool:
        return "DIRECTIONAL" in self.regime

    @property
    def is_volatile(self) -> bool:
        return self.regime == "VOLATILE"

    def prompt_block(self) -> str:
        lines = [
            "=== MARKET REGIME ===",
            f"Regime     : {self.regime}  (confidence {self.confidence}/4)",
            f"Direction  : {self.direction}",
            f"Range      : {self.range_low:.0f} - {self.range_high:.0f}"
            f"  ({self.range_width_pts:.0f} pts)",
            f"VIX        : {self.vix}",
            f"PCR        : {self.pcr}",
            f"Tech trend : {self.tech_trend}",
        ]
        if self.signals:
            lines.append(f"Signals    : {', '.join(self.signals)}")
        if self.strategy:
            lines.append(f"Strategy   : {self.strategy}")
        if self.strategy_detail:
            lines.append(f"Detail     : {self.strategy_detail}")
        if self.no_trade_reason:
            lines.append(f"No trade   : {self.no_trade_reason}")
        lines.append("=====================")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "confidence": self.confidence,
            "direction": self.direction,
            "range_low": self.range_low,
            "range_high": self.range_high,
            "range_width_pts": self.range_width_pts,
            "vix": self.vix,
            "pcr": self.pcr,
            "tech_trend": self.tech_trend,
            "signals": self.signals,
            "strategy": self.strategy,
            "strategy_detail": self.strategy_detail,
            "no_trade_reason": self.no_trade_reason,
        }


def detect_regime(
    pcr: float,
    vix: float,
    tech: Optional[dict] = None,
    spot: float = 0.0,
    sentiment: Optional[str] = None,
    ce_wall: Optional[float] = None,
    pe_wall: Optional[float] = None,
) -> MarketRegime:
    """Classify the current market regime.

    Args:
        pcr: put-call ratio by open interest.
        vix: India VIX level (``0`` if unknown).
        tech: output of ``get_nifty_technicals`` (``ema9``/``ema21``/``vwap``).
        spot: NIFTY spot; falls back to wall levels when 0.
        sentiment: optional pre-computed PCR band; derived from ``pcr`` if absent.
        ce_wall: nearest CE OI wall (upper bound); defaults to ``spot * 1.01``.
        pe_wall: nearest PE OI wall (lower bound); defaults to ``spot * 0.99``.
    """
    tech = tech or {}
    sentiment = sentiment or classify_pcr(pcr)
    spot = spot or tech.get("ltp", 0.0) or 0.0

    signals: List[str] = []
    sideways = 0
    directional = 0

    # Signal 1 - PCR band
    if sentiment in ("MILDLY_BULLISH", "MILDLY_BEARISH"):
        signals.append("PCR_RANGE_BOUND")
        sideways += 1
    elif sentiment in ("BULLISH", "STRONGLY_BULLISH"):
        signals.append("PCR_BULLISH")
        directional += 1
    elif sentiment in ("BEARISH", "STRONGLY_BEARISH"):
        signals.append("PCR_BEARISH")
        directional += 1

    # Signal 2 - OI wall tightness
    range_high = ce_wall if ce_wall else spot * 1.01
    range_low = pe_wall if pe_wall else spot * 0.99
    range_width = range_high - range_low
    if range_width <= _TIGHT_RANGE_PTS:
        signals.append(f"TIGHT_OI_RANGE_{range_low:.0f}-{range_high:.0f}")
        sideways += 1
    elif range_width <= _MODERATE_RANGE_PTS:
        signals.append(f"MODERATE_RANGE_{range_low:.0f}-{range_high:.0f}")
    else:
        signals.append(f"WIDE_RANGE_{range_width:.0f}pts")
        directional += 1

    # Signal 3 - VIX level
    if vix <= 0:
        pass
    elif vix < 14:
        signals.append(f"VIX_LOW_{vix}")
        sideways += 1
    elif vix < 18:
        signals.append(f"VIX_NORMAL_{vix}")
    elif vix < 25:
        signals.append(f"VIX_ELEVATED_{vix}")
        directional += 1
    else:
        signals.append(f"VIX_EXTREME_{vix}")
        directional += 2

    # Signal 4 - technicals
    tech_trend = tech.get("trend", "UNKNOWN")
    ema9 = tech.get("ema9", spot)
    ema21 = tech.get("ema21", spot)
    vwap = tech.get("vwap", spot)
    ema_diff_pct = abs(ema9 - ema21) / ema21 * 100 if ema21 else 0
    price_vs_vwap = abs(spot - vwap) / vwap * 100 if vwap else 0

    if tech_trend == "SIDEWAYS" or (ema_diff_pct < 0.3 and price_vs_vwap < 0.2):
        signals.append("TECH_SIDEWAYS")
        sideways += 1
    elif "UPTREND" in tech_trend or "DOWNTREND" in tech_trend:
        signals.append(f"TECH_{tech_trend}")
        directional += 1

    # Classify
    if vix > 25:
        regime = "VOLATILE"
        confidence = min(4, directional)
    elif sideways >= 3:
        regime = "SIDEWAYS"
        confidence = sideways
    elif directional >= 3:
        regime = "STRONGLY_DIRECTIONAL" if directional >= 4 else "MILDLY_DIRECTIONAL"
        confidence = directional
    else:
        regime = "UNCLEAR"
        confidence = 0

    if sentiment in ("STRONGLY_BULLISH", "BULLISH", "MILDLY_BULLISH"):
        direction = "BULLISH"
    elif sentiment in ("STRONGLY_BEARISH", "BEARISH", "MILDLY_BEARISH"):
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    strategy, detail, no_trade = _pick_strategy(
        regime, direction, spot, range_low, range_high, range_width, vix
    )

    return MarketRegime(
        regime=regime,
        confidence=confidence,
        direction=direction,
        range_low=range_low,
        range_high=range_high,
        range_width_pts=range_width,
        vix=vix,
        pcr=pcr,
        tech_trend=tech_trend,
        signals=signals,
        strategy=strategy,
        strategy_detail=detail,
        no_trade_reason=no_trade,
    )


def _pick_strategy(
    regime: str,
    direction: str,
    spot: float,
    range_low: float,
    range_high: float,
    range_width: float,
    vix: float,
) -> tuple:
    """Returns ``(strategy, detail, no_trade_reason)``."""
    if regime == "VOLATILE":
        if direction == "BULLISH":
            return (
                "BUY_ATM_CE",
                f"VIX {vix} high + bullish; wide SL 40% of premium. "
                f"Target CE wall {range_high:.0f}.",
                "",
            )
        if direction == "BEARISH":
            return (
                "BUY_ATM_PE",
                f"VIX {vix} high + bearish; wide SL 40% of premium. "
                f"Target PE wall {range_low:.0f}.",
                "",
            )
        return (
            "BUY_STRANGLE",
            f"VIX {vix} extreme + no direction; buy CE above range + PE below.",
            "",
        )

    if regime == "SIDEWAYS":
        if range_width <= 200:
            return (
                "SHORT_STRANGLE",
                f"Range {range_low:.0f}-{range_high:.0f} ({range_width:.0f}pts). "
                f"Sell OTM CE near {range_high:.0f} + OTM PE near {range_low:.0f}. "
                "SL: break of range by 30pts. Target: 50% premium.",
                "",
            )
        if range_width <= 350:
            return (
                "IRON_CONDOR",
                f"Range {range_low:.0f}-{range_high:.0f} ({range_width:.0f}pts). "
                f"Sell {range_high:.0f}CE + buy {range_high + 100:.0f}CE; "
                f"sell {range_low:.0f}PE + buy {range_low - 100:.0f}PE.",
                "",
            )
        atm = int(round(spot / 50) * 50)
        return (
            "SHORT_STRADDLE",
            f"Wide range {range_low:.0f}-{range_high:.0f} but sideways. "
            f"Sell ATM {atm}CE + {atm}PE; SL if either leg doubles.",
            "",
        )

    if regime == "STRONGLY_DIRECTIONAL":
        if direction == "BULLISH":
            return (
                "BUY_ATM_CE_AGGRESSIVE",
                f"4+ bullish signals. Buy ATM CE + OTM CE. "
                f"SL below {range_low:.0f} PE wall. Target {range_high:.0f}.",
                "",
            )
        return (
            "BUY_ATM_PE_AGGRESSIVE",
            f"4+ bearish signals. Buy ATM PE + OTM PE. "
            f"SL above {range_high:.0f} CE wall. Target {range_low:.0f}.",
            "",
        )

    if regime == "MILDLY_DIRECTIONAL":
        if direction == "BULLISH":
            return (
                "BUY_OTM_CE",
                f"3 bullish signals. Buy 1 strike OTM CE. SL 30% premium. "
                f"Target {range_high:.0f}.",
                "",
            )
        return (
            "BUY_OTM_PE",
            f"3 bearish signals. Buy 1 strike OTM PE. SL 30% premium. "
            f"Target {range_low:.0f}.",
            "",
        )

    return (
        "",
        "",
        "Mixed signals - wait for a clearer setup before trading.",
    )
