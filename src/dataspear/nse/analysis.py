"""Open-interest analysis for an :class:`OptionChain`.

All functions are pure (no I/O) so they are easy to unit-test and reuse.
"""

from __future__ import annotations

from typing import Dict, List

from dataspear.nse.models import OptionChain, OptionStrike


def pcr_sentiment(pcr: float) -> str:
    """Interpret a Put-Call Ratio."""
    if pcr >= 1.3:
        return "BULLISH - strong PE writing, market well supported"
    if pcr >= 0.9:
        return "NEUTRAL-BULLISH - balanced with slight bullish lean"
    if pcr >= 0.7:
        return "NEUTRAL-BEARISH - mild bearish pressure"
    return "BEARISH - heavy CE writing, resistance overhead"


def max_pain(chain: OptionChain) -> int:
    """Strike at which option writers would lose the least at expiry."""
    strikes = chain.strike_prices
    if not strikes:
        return 0

    best, best_pain = strikes[0], float("inf")
    for candidate in strikes:
        pain = 0.0
        for s in chain.strikes:
            pain += max(s.strike - candidate, 0.0) * s.ce.oi
            pain += max(candidate - s.strike, 0.0) * s.pe.oi
        if pain < best_pain:
            best_pain, best = pain, candidate
    return int(best)


def top_oi_strikes(chain: OptionChain, side: str, n: int = 5) -> List[OptionStrike]:
    """The ``n`` strikes with the highest CE (``side="CE"``) or PE OI."""
    attr = "ce" if side.upper() == "CE" else "pe"
    ranked = sorted(chain.strikes, key=lambda s: getattr(s, attr).oi, reverse=True)
    return ranked[:n]


def _quote_dict(s: OptionStrike, side: str) -> Dict:
    q = s.ce if side.upper() == "CE" else s.pe
    return {
        "strike": int(s.strike),
        "oi": q.oi,
        "change_oi": q.change_oi,
        "iv": q.iv,
        "ltp": q.ltp,
    }


def support_resistance(chain: OptionChain, n: int = 5) -> Dict[str, List[Dict]]:
    """OI-based walls: top PE OI = support, top CE OI = resistance."""
    return {
        "key_resistance": [_quote_dict(s, "CE") for s in top_oi_strikes(chain, "CE", n)],
        "key_support": [_quote_dict(s, "PE") for s in top_oi_strikes(chain, "PE", n)],
    }


def oi_buildup_unwinding(chain: OptionChain, n: int = 3) -> Dict[str, List[Dict]]:
    """Fresh OI writing (change > 0) and unwinding (change < 0) per side."""

    def build(side: str, positive: bool, count: int) -> List[Dict]:
        attr = "ce" if side.upper() == "CE" else "pe"
        rows = [
            s
            for s in chain.strikes
            if (getattr(s, attr).change_oi > 0) == positive
            and getattr(s, attr).change_oi != 0
        ]
        rows.sort(
            key=lambda s: abs(getattr(s, attr).change_oi),
            reverse=True,
        )
        out = []
        for s in rows[:count]:
            q = getattr(s, attr)
            out.append({"strike": int(s.strike), "change_oi": q.change_oi})
        return out

    return {
        "fresh_ce_writing": build("CE", True, n),
        "fresh_pe_writing": build("PE", True, n),
        "ce_unwinding": build("CE", False, n),
        "pe_unwinding": build("PE", False, n),
    }


def iv_skew(chain: OptionChain, span: int = 3) -> List[Dict]:
    """CE/PE implied volatility for +/- ``span`` strikes around ATM."""
    atm = chain.atm_strike()
    if atm is None:
        return []
    prices = chain.strike_prices
    idx = prices.index(atm)
    keep = set(prices[max(0, idx - span) : idx + span + 1])
    return [
        {"strike": int(s.strike), "ce_iv": s.ce.iv, "pe_iv": s.pe.iv}
        for s in chain.strikes
        if s.strike in keep
    ]


def oi_analysis(chain: OptionChain) -> Dict:
    """Full OI summary: PCR, sentiment, max pain, S/R, buildup and IV skew."""
    pcr = chain.pcr
    return {
        "symbol": chain.symbol,
        "expiry": chain.expiry,
        "spot": chain.spot,
        "atm": chain.atm_strike(),
        "pcr": pcr,
        "sentiment": pcr_sentiment(pcr),
        "max_pain": max_pain(chain),
        "ce_oi_total": chain.ce_oi_total,
        "pe_oi_total": chain.pe_oi_total,
        **support_resistance(chain),
        **oi_buildup_unwinding(chain),
        "iv_skew": iv_skew(chain),
    }
