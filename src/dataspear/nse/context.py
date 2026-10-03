"""Full market context in one call.

Builds on :func:`dataspear.nse.scanner.build_market_brief` and adds the rest of
the picture - global indices, FII/DII flows, NIFTY technicals, pre-market gap,
news and the current market session - fetched concurrently. Individual sections
degrade to empty/zeroed values on failure rather than failing the whole call, so
a consumer always gets a usable :class:`MarketContext` back.

    ctx = await build_market_context()
    print(ctx.brief.regime, ctx.brief.strategy, ctx.market_status.phase)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from dataspear.nse.market_extra import (
    get_fii_dii_data,
    get_global_indices,
    get_nifty_technicals,
    get_premarket_data,
)
from dataspear.nse.market_time import MarketStatus, get_market_status
from dataspear.nse.scanner import MarketBrief, build_market_brief
from dataspear.news import NewsArticle, fetch_all_news

log = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """Every section of the market picture, gathered together."""

    brief: MarketBrief
    market_status: MarketStatus
    technicals: dict = field(default_factory=dict)
    global_indices: dict = field(default_factory=dict)
    fii_dii: dict = field(default_factory=dict)
    premarket: dict = field(default_factory=dict)
    news: List[NewsArticle] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "brief": self.brief.to_dict(),
            "market_status": self.market_status.to_dict(),
            "technicals": self.technicals,
            "global_indices": self.global_indices,
            "fii_dii": self.fii_dii,
            "premarket": self.premarket,
            "news": [a.to_dict() for a in self.news],
        }


def _fallback_brief(expiry: Optional[str], error: str) -> MarketBrief:
    return MarketBrief(
        fetched_at="",
        expiry=expiry or "N/A",
        spot=0.0,
        atm=0,
        pcr=0.0,
        sentiment="UNKNOWN",
        max_pain=0,
        vix=0.0,
        error=error,
    )


async def build_market_context(
    expiry: Optional[str] = None,
    direction: str = "BOTH",
    include_news: bool = True,
) -> MarketContext:
    """Gather the full market picture in one call.

    The option-chain brief, technicals, global indices, FII/DII flows,
    pre-market gap and (optionally) news are fetched concurrently.
    """
    status = get_market_status()

    tasks = [
        build_market_brief(expiry=expiry, direction=direction),
        get_nifty_technicals(),
        get_global_indices(),
        get_fii_dii_data(),
        get_premarket_data(),
    ]
    if include_news:
        tasks.append(fetch_all_news(days=1))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    def _section(index: int, default):
        result = results[index]
        if isinstance(result, Exception) or result is None:
            log.warning("market context section %d failed: %s", index, result)
            return default
        return result

    brief = results[0]
    if not isinstance(brief, MarketBrief):
        log.warning("market context brief failed: %s", brief)
        brief = _fallback_brief(expiry, str(brief))

    news = _section(5, []) if include_news else []

    return MarketContext(
        brief=brief,
        market_status=status,
        technicals=_section(1, {}),
        global_indices=_section(2, {}),
        fii_dii=_section(3, {}),
        premarket=_section(4, {}),
        news=news,
    )
