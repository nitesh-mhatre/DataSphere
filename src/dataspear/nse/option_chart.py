"""NSE intraday chart data for a specific NIFTY option strike.

The NSE chart endpoint returns a price/volume time series for one contract.
Contracts are addressed with an identifier like::

    OPTIDXNIFTY05-05-2026CE24000.00

i.e. ``OPTIDXNIFTY{DD-MM-YYYY}{CE|PE}{STRIKE:.2f}``. Use
:func:`get_option_chart` (one leg) or :func:`get_both_charts` (CE + PE).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple

from dataspear.settings import NSE_BASE_URL
from dataspear.nse.session import nse_get
from dataspear.utils.time import to_ist

log = logging.getLogger(__name__)

CHART_URL = f"{NSE_BASE_URL}/api/chart-databyindex?index={{identifier}}"


@dataclass
class ChartPoint:
    """One timestamped price/volume sample."""

    timestamp: datetime
    price: float
    volume: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "volume": self.volume,
        }


@dataclass
class OptionChart:
    """Intraday time series for a single option contract."""

    identifier: str = ""
    expiry: str = ""
    strike: float = 0.0
    option_type: str = "CE"
    close_price: float = 0.0
    points: List[ChartPoint] = field(default_factory=list)

    @property
    def last_price(self) -> float:
        return self.points[-1].price if self.points else 0.0

    @property
    def high(self) -> float:
        return max((p.price for p in self.points), default=0.0)

    @property
    def low(self) -> float:
        return min((p.price for p in self.points), default=0.0)

    @property
    def total_volume(self) -> int:
        return sum(p.volume for p in self.points)

    def trend(self, window_pct: float = 0.2) -> str:
        """UP/DOWN/FLAT from the first vs last ``window_pct`` of the series."""
        n = len(self.points)
        if n < 5:
            return "FLAT"
        window = max(1, int(n * window_pct))
        early = sum(p.price for p in self.points[:window]) / window
        late = sum(p.price for p in self.points[-window:]) / window
        if late > early * 1.005:
            return "UP"
        if late < early * 0.995:
            return "DOWN"
        return "FLAT"

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "expiry": self.expiry,
            "strike": self.strike,
            "option_type": self.option_type,
            "close_price": self.close_price,
            "last_price": self.last_price,
            "high": self.high,
            "low": self.low,
            "total_volume": self.total_volume,
            "points": [p.to_dict() for p in self.points],
        }


# Expiry formats seen in the wild: contract-info returns ``06-Oct-2026`` while
# the option-chain rows carry ``06-10-2026`` (DD-MM-YYYY).
_EXPIRY_FORMATS = ("%d-%b-%Y", "%d-%m-%Y", "%d-%B-%Y", "%Y-%m-%d")


def _parse_expiry(expiry: str) -> datetime:
    for fmt in _EXPIRY_FORMATS:
        try:
            return datetime.strptime(expiry, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Unrecognised expiry {expiry!r}; expected one of DD-Mon-YYYY or DD-MM-YYYY"
    )


def build_identifier(expiry: str, strike: float, option_type: str = "CE") -> str:
    """Build the NSE chart identifier for a contract.

    Args:
        expiry: ``DD-Mon-YYYY`` e.g. ``"05-May-2026"`` or ``DD-MM-YYYY``
            e.g. ``"06-10-2026"`` (both are produced by NSE endpoints).
        strike: strike price e.g. ``24000``.
        option_type: ``"CE"`` or ``"PE"``.
    """
    dt = _parse_expiry(expiry)
    return (
        f"OPTIDXNIFTY{dt.strftime('%d-%m-%Y')}"
        f"{option_type.upper()}{float(strike):.2f}"
    )


def _to_ist(ms: float) -> datetime:
    return to_ist(ms / 1000.0)


def parse_chart_data(
    raw: dict,
    identifier: str = "",
    expiry: str = "",
    strike: float = 0.0,
    option_type: str = "CE",
) -> OptionChart:
    """Parse a raw NSE chart payload (note NSE's ``grapthData`` typo)."""
    graph = (raw or {}).get("grapthData") or (raw or {}).get("graphData") or []
    volume_data = (raw or {}).get("volume") or []

    volume_by_ts = {}
    for row in volume_data:
        try:
            volume_by_ts[int(row[0])] = int(row[1])
        except (TypeError, ValueError, IndexError):
            continue

    points: List[ChartPoint] = []
    for row in graph:
        try:
            ts_ms, price = int(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        points.append(
            ChartPoint(
                timestamp=_to_ist(ts_ms),
                price=round(price, 2),
                volume=volume_by_ts.get(ts_ms, 0),
            )
        )
    points.sort(key=lambda p: p.timestamp)

    return OptionChart(
        identifier=identifier,
        expiry=expiry,
        strike=float(strike),
        option_type=option_type.upper(),
        close_price=float((raw or {}).get("closePrice") or 0.0),
        points=points,
    )


async def fetch_option_chart(
    expiry: str, strike: float, option_type: str = "CE"
) -> OptionChart:
    """Fetch and parse the intraday chart for one option contract."""
    identifier = build_identifier(expiry, strike, option_type)
    resp = await nse_get(CHART_URL.format(identifier=identifier))
    return parse_chart_data(
        resp.json(),
        identifier=identifier,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
    )


async def get_option_chart(
    expiry: str, strike: float, option_type: str = "CE"
) -> OptionChart:
    """Alias for :func:`fetch_option_chart` for module consumers."""
    return await fetch_option_chart(expiry, strike, option_type)


async def get_both_charts(
    expiry: str, strike: float
) -> Tuple[OptionChart, OptionChart]:
    """Fetch CE and PE charts for the same strike. Returns ``(ce, pe)``."""
    ce = await fetch_option_chart(expiry, strike, "CE")
    pe = await fetch_option_chart(expiry, strike, "PE")
    return ce, pe
