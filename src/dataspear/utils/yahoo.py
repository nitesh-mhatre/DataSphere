"""Async Yahoo Finance chart client built on httpx.

Yahoo's public chart endpoint returns OHLCV plus quote metadata and needs no
API key. It backs NIFTY spot, India VIX, global indices and intraday
technicals, keeping dataspear free of the heavy ``yfinance``/``pandas`` stack.

    meta, candles = await fetch_chart("^INDIAVIX", range_="10d", interval="1d")

Use :func:`get_quote` for a simple last-price/previous-close snapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from dataspear.settings import (
    DEFAULT_HTTP_TIMEOUT,
    JSON_HEADERS,
    YAHOO_CHART_ENDPOINT,
)
from dataspear.utils.http import get_response

log = logging.getLogger(__name__)

YAHOO_CHART_URL = YAHOO_CHART_ENDPOINT

_HEADERS = JSON_HEADERS
_DEFAULT_TIMEOUT = DEFAULT_HTTP_TIMEOUT


@dataclass
class Candle:
    """A single Yahoo OHLCV candle."""

    timestamp: int = 0  # epoch seconds (UTC)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    @property
    def wick_up(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def wick_down(self) -> float:
        return min(self.open, self.close) - self.low

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


def _at(values: List[Any], index: int) -> Optional[float]:
    if index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_chart(payload: Optional[dict]) -> Tuple[Dict[str, Any], List[Candle]]:
    """Parse a raw Yahoo chart payload into ``(meta, candles)``.

    Rows with a missing close price (Yahoo's null padding) are skipped.
    """
    result = ((payload or {}).get("chart") or {}).get("result") or []
    if not result:
        return {}, []

    item = result[0] or {}
    meta = item.get("meta") or {}
    timestamps = item.get("timestamp") or []
    quote = (((item.get("indicators") or {}).get("quote")) or [{}])[0]

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    candles: List[Candle] = []
    for i, ts in enumerate(timestamps):
        close = _at(closes, i)
        if close is None:
            continue
        open_ = _at(opens, i)
        high = _at(highs, i)
        low = _at(lows, i)
        volume = _at(volumes, i)
        candles.append(
            Candle(
                timestamp=int(ts),
                open=open_ if open_ is not None else close,
                high=high if high is not None else close,
                low=low if low is not None else close,
                close=close,
                volume=int(volume) if volume is not None else 0,
            )
        )
    return meta, candles


async def fetch_chart(
    ticker: str,
    range_: str = "5d",
    interval: str = "1d",
    timeout: float = _DEFAULT_TIMEOUT,
) -> Optional[dict]:
    """Fetch the raw Yahoo chart payload for ``ticker``.

    Returns ``None`` (and logs) on any network/HTTP failure so callers can
    degrade gracefully.
    """
    url = YAHOO_CHART_URL.format(ticker=ticker)
    params = {"range": range_, "interval": interval, "includePrePost": "false"}
    try:
        response = await get_response(
            url, params=params, headers=_HEADERS, timeout=timeout
        )
        return response.json()
    except httpx.HTTPError as exc:
        log.warning("Yahoo chart fetch failed for %s: %s", ticker, exc)
    except ValueError as exc:  # invalid JSON
        log.warning("Yahoo chart decode failed for %s: %s", ticker, exc)
    return None


async def get_candles(
    ticker: str,
    range_: str = "5d",
    interval: str = "1d",
    timeout: float = _DEFAULT_TIMEOUT,
) -> List[Candle]:
    """Convenience wrapper returning just the parsed candles."""
    payload = await fetch_chart(
        ticker, range_=range_, interval=interval, timeout=timeout
    )
    _, candles = parse_chart(payload)
    return candles


def quote_from_meta(meta: Dict[str, Any]) -> dict:
    """Build a ``{price, prev_close, change, change_pct}`` snapshot from meta."""
    price = _to_float(meta.get("regularMarketPrice"))
    prev = _to_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
    if prev <= 0:
        prev = price
    change = round(price - prev, 2)
    change_pct = round(change / prev * 100, 2) if prev else 0.0
    return {
        "price": round(price, 2),
        "prev_close": round(prev, 2),
        "change": change,
        "change_pct": change_pct,
    }


async def get_quote(
    ticker: str,
    range_: str = "1d",
    interval: str = "1d",
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict:
    """Return a last-price snapshot for ``ticker`` (zeros on failure)."""
    payload = await fetch_chart(
        ticker, range_=range_, interval=interval, timeout=timeout
    )
    meta, candles = parse_chart(payload)
    if not meta and not candles:
        return {"price": 0.0, "prev_close": 0.0, "change": 0.0, "change_pct": 0.0}
    if not meta.get("regularMarketPrice") and candles:
        meta = {**meta, "regularMarketPrice": candles[-1].close}
    return quote_from_meta(meta)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
