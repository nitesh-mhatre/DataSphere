"""Price-level detection from OHLC candles.

Pure functions (no I/O) that surface the levels institutional flow tends to
respect:

* swing highs / lows          - structural pivots
* wick ("stop-hunt") levels    - round-number zones with repeated long wicks
* distribution / accumulation  - high-volume rejection zones
* opening fake frequency       - indecisive daily candles

Levels are rounded to the nearest ``step`` (default 50 for NIFTY) so they line
up with option strike walls. Combine with
:func:`dataspear.nse.analysis.support_resistance` for an OI + price view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from dataspear.utils.time import to_ist
from dataspear.utils.yahoo import Candle

DEFAULT_STEP = 50.0


def _round_level(price: float, step: float = DEFAULT_STEP) -> float:
    if step <= 0:
        return round(price, 2)
    return round(round(price / step) * step, 2)


def swing_highs(candles: List[Candle], n: int = 3, limit: int = 5) -> List[float]:
    """Return recent swing-high pivots (higher than ``n`` candles either side)."""
    highs: List[float] = []
    for i in range(n, len(candles) - n):
        c = candles[i]
        if all(c.high >= candles[i - j].high for j in range(1, n + 1)) and all(
            c.high >= candles[i + j].high for j in range(1, n + 1)
        ):
            highs.append(round(c.high, 2))
    return highs[-limit:]


def swing_lows(candles: List[Candle], n: int = 3, limit: int = 5) -> List[float]:
    """Return recent swing-low pivots (lower than ``n`` candles either side)."""
    lows: List[float] = []
    for i in range(n, len(candles) - n):
        c = candles[i]
        if all(c.low <= candles[i - j].low for j in range(1, n + 1)) and all(
            c.low <= candles[i + j].low for j in range(1, n + 1)
        ):
            lows.append(round(c.low, 2))
    return lows[-limit:]


def wick_levels(
    candles: List[Candle],
    threshold_wick: float = 25.0,
    min_hits: int = 2,
    step: float = DEFAULT_STEP,
) -> List[float]:
    """Round-number zones hit by recurring long wicks (stop-hunt candidates).

    A level qualifies once at least ``min_hits`` candles show a wick longer
    than ``threshold_wick`` near it. Returned highest-first.
    """
    counts: Dict[float, int] = {}
    for c in candles:
        if c.wick_up > threshold_wick:
            lvl = _round_level(c.high, step)
            counts[lvl] = counts.get(lvl, 0) + 1
        if c.wick_down > threshold_wick:
            lvl = _round_level(c.low, step)
            counts[lvl] = counts.get(lvl, 0) + 1
    return sorted(
        [lvl for lvl, cnt in counts.items() if cnt >= min_hits], reverse=True
    )


def distribution_accumulation_zones(
    candles: List[Candle],
    lookback: int = 20,
    vol_mult: float = 1.5,
    step: float = DEFAULT_STEP,
) -> Dict[str, List[float]]:
    """Split high-volume rejection candles into distribution / accumulation.

    Upper wick on high volume marks distribution (supply); lower wick marks
    accumulation (demand).
    """
    window = candles[-lookback:]
    if not window:
        return {"distribution": [], "accumulation": []}

    avg_vol = sum(c.volume for c in window) / len(window)
    distribution: List[float] = []
    accumulation: List[float] = []
    for c in window:
        if avg_vol and c.volume > avg_vol * vol_mult:
            if c.wick_up > c.body:
                distribution.append(_round_level(c.high, step))
            elif c.wick_down > c.body:
                accumulation.append(_round_level(c.low, step))

    return {
        "distribution": sorted(set(distribution), reverse=True)[:3],
        "accumulation": sorted(set(accumulation))[:3],
    }


def opening_fake_frequency(candles: List[Candle], lookback: int = 5) -> int:
    """Count recent daily candles with a small body relative to total range."""
    count = 0
    for c in candles[-lookback:]:
        if c.total_range > 0 and c.body / c.total_range < 0.35:
            count += 1
    return count


def time_of_day_traps(
    candles: List[Candle], hour: int = 9, minute: int = 30, window_min: int = 30
) -> List[str]:
    """Flag repeated stop-hunt wicks in the opening window (default 09:30)."""
    start = hour * 60 + minute
    openers = []
    for c in candles:
        dt = to_ist(c.timestamp)
        mins = dt.hour * 60 + dt.minute
        if start <= mins < start + window_min:
            openers.append(c)

    traps: List[str] = []
    if openers:
        long_wick = sum(
            1 for c in openers if max(c.wick_up, c.wick_down) > c.body * 2
        )
        if long_wick >= 3:
            traps.append(
                f"{hour:02d}:{minute:02d}-{(start + window_min) // 60:02d}:"
                f"{(start + window_min) % 60:02d}: {long_wick}/{len(openers)} "
                f"candles had stop-hunt wicks"
            )
    return traps


@dataclass
class LevelAnalysis:
    """Detected structural levels plus a short human-readable summary."""

    swing_highs: List[float] = field(default_factory=list)
    swing_lows: List[float] = field(default_factory=list)
    stop_hunt_levels: List[float] = field(default_factory=list)
    distribution_zones: List[float] = field(default_factory=list)
    accumulation_zones: List[float] = field(default_factory=list)
    opening_fake_frequency: int = 0
    time_of_day_traps: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "swing_highs": self.swing_highs,
            "swing_lows": self.swing_lows,
            "stop_hunt_levels": self.stop_hunt_levels,
            "distribution_zones": self.distribution_zones,
            "accumulation_zones": self.accumulation_zones,
            "opening_fake_frequency": self.opening_fake_frequency,
            "time_of_day_traps": self.time_of_day_traps,
            "summary": self.summary,
        }


def detect_levels(
    candle_sets: List[List[Candle]],
    step: float = DEFAULT_STEP,
    stop_hunt_wick: float = 25.0,
    opening_fakes_days: int = 5,
) -> LevelAnalysis:
    """Detect levels across multiple timeframes.

    ``candle_sets`` is ordered from intraday to daily (e.g. ``[30m, daily]``).
    Swing pivots and opening-fake frequency come from the highest timeframe
    available; stop-hunt wicks are aggregated across all of them.
    """
    sets = [c for c in candle_sets if c]
    if not sets:
        return LevelAnalysis(summary="No candles supplied.")

    daily = sets[-1]
    stop_hunt: List[float] = []
    for cs in sets:
        stop_hunt.extend(wick_levels(cs, threshold_wick=stop_hunt_wick, step=step))
    stop_hunt = sorted(set(stop_hunt), reverse=True)[:5]

    zones = distribution_accumulation_zones(
        sets[0] if len(sets) > 1 else daily, step=step
    )

    traps: List[str] = []
    for cs in sets:
        traps.extend(time_of_day_traps(cs))

    s_highs = swing_highs(daily, limit=5) if len(daily) >= 7 else []
    s_lows = swing_lows(daily, limit=5) if len(daily) >= 7 else []
    fake_freq = opening_fake_frequency(daily, lookback=opening_fakes_days)

    parts = []
    if stop_hunt:
        parts.append(f"Stop-hunt zones at {stop_hunt[:2]}.")
    if s_highs:
        parts.append(f"Swing highs: {s_highs[-2:]}.")
    if s_lows:
        parts.append(f"Swing lows: {s_lows[:2]}.")
    if fake_freq >= 2:
        parts.append(f"Opening fake pattern seen {fake_freq}/5 days.")
    summary = " ".join(parts) or "No significant levels detected."

    return LevelAnalysis(
        swing_highs=s_highs,
        swing_lows=s_lows,
        stop_hunt_levels=stop_hunt,
        distribution_zones=zones["distribution"],
        accumulation_zones=zones["accumulation"],
        opening_fake_frequency=fake_freq,
        time_of_day_traps=traps,
        summary=summary,
    )


def merge_with_oi_walls(
    levels: LevelAnalysis, support: List[dict], resistance: List[dict]
) -> dict:
    """Combine price levels with OI walls into one support/resistance view."""
    return {
        "oi_resistance": [r.get("strike") for r in resistance],
        "oi_support": [s.get("strike") for s in support],
        "swing_highs": levels.swing_highs,
        "swing_lows": levels.swing_lows,
        "stop_hunt_levels": levels.stop_hunt_levels,
        "distribution_zones": levels.distribution_zones,
        "accumulation_zones": levels.accumulation_zones,
    }
