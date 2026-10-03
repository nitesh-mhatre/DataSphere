"""India VIX data: spot, recent history, trend and regime.

India VIX is the market's fear gauge. Rising VIX means option buyers get more
value while premium sellers take on more risk; the regime helpers here turn
that into a coarse label plus a strategy note.

Source: Yahoo Finance (``^INDIAVIX``) via :mod:`dataspear.utils.yahoo`.
"""

from __future__ import annotations

import logging
from typing import List

from dataspear.utils.yahoo import get_candles, get_quote

log = logging.getLogger(__name__)

VIX_TICKER = "^INDIAVIX"

# Regime thresholds on the absolute VIX level.
LOW_FEAR_MAX = 13.0
NORMAL_MAX = 18.0
ELEVATED_MAX = 25.0

_STRATEGY_NOTE = {
    "LOW_FEAR": (
        "VIX low -> sell options (strangles/condors). "
        "Premiums underpriced for buyers."
    ),
    "NORMAL": "VIX normal -> directional trades viable. Balance buy/sell.",
    "ELEVATED": "VIX elevated -> buy options only. Sellers exposed to big moves.",
    "EXTREME_FEAR": "VIX extreme -> no new trades. Close positions.",
}


def vix_regime(vix: float) -> str:
    """Classify a VIX level into LOW_FEAR / NORMAL / ELEVATED / EXTREME_FEAR."""
    if vix <= 0:
        return "UNKNOWN"
    if vix < LOW_FEAR_MAX:
        return "LOW_FEAR"
    if vix < NORMAL_MAX:
        return "NORMAL"
    if vix < ELEVATED_MAX:
        return "ELEVATED"
    return "EXTREME_FEAR"


async def get_india_vix() -> float:
    """Current India VIX level. Returns ``0.0`` on failure."""
    quote_ = await get_quote(VIX_TICKER)
    return float(quote_.get("price", 0.0))


async def get_india_vix_history(days: int = 5) -> dict:
    """VIX trend over the last ``days`` sessions.

    Returns a dict with ``current``, ``prev_close``, ``change``, ``avg_5d``,
    ``trend`` (RISING/FALLING), ``regime``, ``history`` and ``strategy_note``.
    """
    candles = await get_candles(VIX_TICKER, range_=f"{days + 2}d", interval="1d")
    closes: List[float] = [round(c.close, 2) for c in candles if c.close > 0]

    if len(closes) < 2:
        return {
            "current": 0.0,
            "prev_close": 0.0,
            "change": 0.0,
            "avg_5d": 0.0,
            "trend": "UNKNOWN",
            "regime": "UNKNOWN",
            "history": closes,
            "strategy_note": "",
            "error": "Insufficient VIX history",
        }

    window = closes[-days:]
    current = window[-1]
    prev = closes[-2]
    avg = round(sum(window) / len(window), 2)
    change = round(current - prev, 2)
    trend = "RISING" if window[-1] > window[0] else "FALLING"
    regime = vix_regime(current)

    return {
        "current": current,
        "prev_close": prev,
        "change": change,
        "avg_5d": avg,
        "trend": trend,
        "regime": regime,
        "history": window,
        "strategy_note": _STRATEGY_NOTE.get(regime, ""),
    }


async def get_spot_and_vix() -> dict:
    """NIFTY spot and India VIX in one round trip each."""
    from dataspear.utils.yahoo import get_quote as _quote

    spot = await _quote("^NSEI")
    vix = await get_quote(VIX_TICKER)
    return {
        "spot": float(spot.get("price", 0.0)),
        "vix": float(vix.get("price", 0.0)),
        "vix_change": float(vix.get("change", 0.0)),
    }
