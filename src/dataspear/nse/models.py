"""Data models for the NSE option chain.

These are plain dataclasses (no pandas) so the data layer stays lightweight
and easy to consume from other projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OptionQuote:
    """One side (CE or PE) of a single strike."""

    oi: int = 0
    change_oi: int = 0
    volume: int = 0
    iv: float = 0.0
    ltp: float = 0.0
    change: float = 0.0
    bid: float = 0.0
    ask: float = 0.0

    @property
    def oi_change_pct(self) -> float:
        prev_oi = self.oi - self.change_oi
        if prev_oi <= 0:
            return 0.0
        return round(self.change_oi / prev_oi * 100, 2)

    def to_dict(self) -> dict:
        return {
            "oi": self.oi,
            "change_oi": self.change_oi,
            "volume": self.volume,
            "iv": self.iv,
            "ltp": self.ltp,
            "change": self.change,
            "bid": self.bid,
            "ask": self.ask,
        }


@dataclass
class OptionStrike:
    """A single strike row with both call and put legs."""

    strike: float
    expiry: str = ""
    ce: OptionQuote = field(default_factory=OptionQuote)
    pe: OptionQuote = field(default_factory=OptionQuote)

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "expiry": self.expiry,
            "ce": self.ce.to_dict(),
            "pe": self.pe.to_dict(),
        }


@dataclass
class OptionChain:
    """Parsed NSE NIFTY option chain plus convenience aggregates."""

    symbol: str = "NIFTY"
    spot: float = 0.0
    expiry: str = ""
    strikes: List[OptionStrike] = field(default_factory=list)

    # ── Aggregates ────────────────────────────────────────────────────────────

    @property
    def ce_oi_total(self) -> int:
        return sum(s.ce.oi for s in self.strikes)

    @property
    def pe_oi_total(self) -> int:
        return sum(s.pe.oi for s in self.strikes)

    @property
    def pcr(self) -> float:
        """Put-Call Ratio by total open interest."""
        if not self.ce_oi_total:
            return 0.0
        return round(self.pe_oi_total / self.ce_oi_total, 2)

    @property
    def strike_prices(self) -> List[float]:
        return sorted({s.strike for s in self.strikes})

    def atm_strike(self) -> Optional[float]:
        """Strike closest to spot (falls back to the median strike)."""
        prices = self.strike_prices
        if not prices:
            return None
        if not self.spot:
            return prices[len(prices) // 2]
        return min(prices, key=lambda p: abs(p - self.spot))

    def filter_atm(self, n: int) -> "OptionChain":
        """Return a copy keeping only +/- n strikes around the ATM strike."""
        atm = self.atm_strike()
        if atm is None:
            return self
        prices = self.strike_prices
        idx = prices.index(atm)
        keep = set(prices[max(0, idx - n) : idx + n + 1])
        return OptionChain(
            symbol=self.symbol,
            spot=self.spot,
            expiry=self.expiry,
            strikes=[s for s in self.strikes if s.strike in keep],
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "spot": self.spot,
            "expiry": self.expiry,
            "atm_strike": self.atm_strike(),
            "pcr": self.pcr,
            "ce_oi_total": self.ce_oi_total,
            "pe_oi_total": self.pe_oi_total,
            "strikes": [s.to_dict() for s in self.strikes],
        }
