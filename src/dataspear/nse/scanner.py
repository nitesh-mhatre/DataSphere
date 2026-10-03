"""MarketBrief: one compact, pre-digested snapshot of the NIFTY tape.

Orchestrates the data layer into a single object:

* option chain + OI analysis (PCR, max pain, walls, fresh writing)
* India VIX
* targeted strikes with intraday chart data (ATM +/- based on sentiment)

Consumers get everything they need in one call instead of chasing individual
endpoints.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from dataspear.nse.analysis import (
    max_pain,
    oi_buildup_unwinding,
    support_resistance,
)
from dataspear.nse.models import OptionChain
from dataspear.nse.market_time import get_market_status
from dataspear.nse.option_chain import get_expiry_dates, get_nifty_option_chain
from dataspear.nse.option_chart import get_option_chart
from dataspear.nse.regime import classify_pcr, detect_regime
from dataspear.nse.vix import get_india_vix, vix_regime
from dataspear.utils.time import now_ist

log = logging.getLogger(__name__)


def _oi_buildup(oi: int, chng_oi: int) -> str:
    if oi <= 0:
        return "STABLE"
    if chng_oi > oi * 0.05:
        return "BUILDING"
    if chng_oi < -oi * 0.05:
        return "UNWINDING"
    return "STABLE"


@dataclass
class StrikeBrief:
    """Compact data for one targeted strike with chart context."""

    strike: int
    option_type: str
    ltp: float = 0.0
    prev_close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    oi: int = 0
    chng_oi: int = 0
    iv: float = 0.0
    volume: int = 0
    price_chng_pct: float = 0.0
    oi_buildup: str = "STABLE"
    trend: str = "FLAT"

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "option_type": self.option_type,
            "ltp": self.ltp,
            "prev_close": self.prev_close,
            "high": self.high,
            "low": self.low,
            "oi": self.oi,
            "chng_oi": self.chng_oi,
            "iv": self.iv,
            "volume": self.volume,
            "price_chng_pct": self.price_chng_pct,
            "oi_buildup": self.oi_buildup,
            "trend": self.trend,
        }


@dataclass
class MarketBrief:
    """Everything needed for a decision, in one compact object."""

    fetched_at: str
    expiry: str
    spot: float
    atm: int
    pcr: float
    sentiment: str
    max_pain: int
    vix: float
    vix_regime: str = "UNKNOWN"
    regime: str = "UNCLEAR"
    strategy: str = ""
    market_phase: str = ""
    market_open: bool = False
    resistance: List[dict] = field(default_factory=list)
    support: List[dict] = field(default_factory=list)
    fresh_ce_writing: List[dict] = field(default_factory=list)
    fresh_pe_writing: List[dict] = field(default_factory=list)
    targeted: List[StrikeBrief] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "fetched_at": self.fetched_at,
            "expiry": self.expiry,
            "spot": self.spot,
            "atm": self.atm,
            "pcr": self.pcr,
            "sentiment": self.sentiment,
            "max_pain": self.max_pain,
            "vix": self.vix,
            "vix_regime": self.vix_regime,
            "regime": self.regime,
            "strategy": self.strategy,
            "market_phase": self.market_phase,
            "market_open": self.market_open,
            "resistance": self.resistance,
            "support": self.support,
            "fresh_ce_writing": self.fresh_ce_writing,
            "fresh_pe_writing": self.fresh_pe_writing,
            "targeted": [t.to_dict() for t in self.targeted],
            "error": self.error,
        }


def select_target_strikes(
    chain: OptionChain, sentiment: str, direction: str = "BOTH", max_strikes: int = 3
) -> List[Tuple[int, str]]:
    """Pick 2-3 (strike, option_type) targets from the chain's real strikes."""
    strikes = [int(s) for s in chain.strike_prices]
    if not strikes:
        return []
    atm = chain.atm_strike()
    if atm is None:
        return []
    atm = int(atm)
    above = [s for s in strikes if s >= atm]
    below = [s for s in strikes if s <= atm]

    def nearest_above(n: int = 1) -> Optional[int]:
        return above[n] if len(above) > n else None

    def nearest_below(n: int = 1) -> Optional[int]:
        idx = len(below) - 1 - n
        return below[idx] if idx >= 0 else None

    bullish = "BULLISH" in sentiment
    bearish = "BEARISH" in sentiment
    sideways = sentiment in ("MILDLY_BULLISH", "MILDLY_BEARISH")
    targets: List[Tuple[int, str]] = []

    if sideways:
        ce = nearest_above(1)
        pe = nearest_below(1)
        if ce:
            targets.append((ce, "CE"))
        if pe:
            targets.append((pe, "PE"))
    elif direction == "SELL":
        if bullish:
            for s in (nearest_below(1), nearest_below(2)):
                if s:
                    targets.append((s, "PE"))
        else:
            for s in (nearest_above(1), nearest_above(2)):
                if s:
                    targets.append((s, "CE"))
    else:  # BUY or BOTH
        if bullish:
            targets.append((atm, "CE"))
            pe = nearest_below(1)
            if pe:
                targets.append((pe, "PE"))
        elif bearish:
            targets.append((atm, "PE"))
            ce = nearest_above(1)
            if ce:
                targets.append((ce, "CE"))
        else:
            targets.append((atm, "CE"))

    seen, unique = set(), []
    for t in targets:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:max_strikes]


async def _strike_brief(
    expiry: str, strike: int, option_type: str, chain: OptionChain
) -> Optional[StrikeBrief]:
    strike_row = next((s for s in chain.strikes if int(s.strike) == strike), None)
    quote = None
    if strike_row is not None:
        quote = strike_row.ce if option_type == "CE" else strike_row.pe
    oi = quote.oi if quote else 0
    chng_oi = quote.change_oi if quote else 0
    iv = quote.iv if quote else 0.0
    oc_ltp = quote.ltp if quote else 0.0

    try:
        chart = await get_option_chart(expiry, strike, option_type)
    except Exception as exc:  # noqa: BLE001 - chart is best-effort
        log.warning("chart fetch failed for %s%s: %s", strike, option_type, exc)
        chart = None

    if chart is None or not chart.points:
        return StrikeBrief(
            strike=strike,
            option_type=option_type,
            ltp=round(oc_ltp, 2),
            oi=oi,
            chng_oi=chng_oi,
            iv=round(iv, 2),
            oi_buildup=_oi_buildup(oi, chng_oi),
            trend="FLAT",
        )

    open_price = chart.points[0].price
    if open_price:
        pct = round((chart.last_price - open_price) / open_price * 100, 2)
    else:
        pct = 0.0
    return StrikeBrief(
        strike=strike,
        option_type=option_type,
        ltp=round(chart.last_price, 2),
        prev_close=round(chart.close_price, 2),
        high=round(chart.high, 2),
        low=round(chart.low, 2),
        oi=oi,
        chng_oi=chng_oi,
        iv=round(iv, 2),
        volume=chart.total_volume,
        price_chng_pct=pct,
        oi_buildup=_oi_buildup(oi, chng_oi),
        trend=chart.trend(),
    )


async def build_market_brief(
    expiry: Optional[str] = None,
    direction: str = "BOTH",
    fetch_charts: bool = True,
) -> MarketBrief:
    """Fetch a fresh :class:`MarketBrief` for the given (or nearest) expiry."""
    fetched_at = now_ist().strftime("%H:%M:%S")
    try:
        if expiry is None:
            dates = await get_expiry_dates()
            expiry = dates[0] if dates else None
        chain = await get_nifty_option_chain(expiry=expiry)
        if not chain.strikes:
            raise ValueError("Empty option chain from NSE")

        expiry_str = chain.expiry or (expiry or "N/A")
        vix = await get_india_vix()
        sentiment = classify_pcr(chain.pcr)

        sr = support_resistance(chain, n=2)
        fresh = oi_buildup_unwinding(chain, n=2)
        atm = chain.atm_strike()

        status = get_market_status()
        ce_wall = sr["key_resistance"][0]["strike"] if sr["key_resistance"] else None
        pe_wall = sr["key_support"][0]["strike"] if sr["key_support"] else None
        regime = detect_regime(
            pcr=chain.pcr,
            vix=vix,
            spot=chain.spot,
            sentiment=sentiment,
            ce_wall=ce_wall,
            pe_wall=pe_wall,
        )

        targeted: List[StrikeBrief] = []
        if fetch_charts:
            targets = select_target_strikes(chain, sentiment, direction)
            results = await asyncio.gather(
                *(_strike_brief(expiry_str, s, t, chain) for s, t in targets),
                return_exceptions=True,
            )
            for res in results:
                if isinstance(res, StrikeBrief):
                    targeted.append(res)

        return MarketBrief(
            fetched_at=fetched_at,
            expiry=expiry_str,
            spot=round(chain.spot, 2),
            atm=int(atm) if atm is not None else 0,
            pcr=chain.pcr,
            sentiment=sentiment,
            max_pain=max_pain(chain),
            vix=vix,
            vix_regime=vix_regime(vix),
            regime=regime.regime,
            strategy=regime.strategy,
            market_phase=status.phase,
            market_open=status.is_open,
            resistance=sr["key_resistance"],
            support=sr["key_support"],
            fresh_ce_writing=fresh["fresh_ce_writing"],
            fresh_pe_writing=fresh["fresh_pe_writing"],
            targeted=targeted,
        )
    except Exception as exc:  # noqa: BLE001 - return a partial brief
        log.error("build_market_brief failed: %s", exc, exc_info=True)
        return MarketBrief(
            fetched_at=fetched_at,
            expiry=expiry or "N/A",
            spot=0.0,
            atm=0,
            pcr=0.0,
            sentiment="UNKNOWN",
            max_pain=0,
            vix=0.0,
            error=str(exc),
        )
