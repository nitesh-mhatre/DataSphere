"""Groww (groww.in) market data built on httpx.

This module mirrors the NSE features but sources everything from Groww's public
web endpoints, which need no API key:

* ``option expiries``   - ``GET /options/{underlying}``
* ``option chain``      - same page, ``?expiry=YYYY-MM-DD`` for any expiry
* ``intraday chart``    - ``/v1/api/charting_service/.../segment/{CASH|FNO}/{symbol}``
                        (CASH/index candles work; Groww carries no FNO
                        candles, so option charts fall back to NSE)
* ``levels``            - Groww candles fed through :func:`dataspear.nse.levels.detect_levels`

Groww addresses derivatives with its own contract id, e.g. ``NIFTY26O0623000PE``
(weekly) or ``NIFTY26OCT23000PE`` (monthly). Use
:func:`get_groww_option_chain` to read the exact ``contract_id`` for a strike,
or :func:`build_groww_symbol` to construct one.

Example:
    from dataspear.groww import (
        get_groww_expiries,
        get_groww_option_chain,
        get_groww_option_chart,
    )

    expiries = await get_groww_expiries("NIFTY")
    chain = await get_groww_option_chain("NIFTY", expiry=expiries[0])
    chart = await get_groww_option_chart(expiries[0], 23000, "PE")
"""

from __future__ import annotations

import logging
import re
import time as _time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

import httpx

from dataspear.settings import GROWW_BASE_URL, GROWW_HEADERS, GROWW_HTTP_TIMEOUT
from dataspear.utils.http import get_json, get_text
from dataspear.utils.time import IST, to_ist

log = logging.getLogger(__name__)

GROWW_BASE = GROWW_BASE_URL
CHART_URL = (
    f"{GROWW_BASE}/v1/api/charting_service/v2/chart/delayed"
    "/exchange/NSE/segment/{segment}/{symbol}"
)
OPTION_CHAIN_URL = f"{GROWW_BASE}/options/{{underlying}}"
LIVE_PRICE_URL = (
    f"{GROWW_BASE}/v1/api/stocks_fo_data/v1/tr_live_prices"
    "/exchange/{exchange}/segment/{segment}/{symbol}/latest"
)

# Groww uses a single letter for weekly expiries and the 3-letter month for the
# monthly contract: NIFTY26O0623000PE vs NIFTY26OCT23000PE.
_MONTH_LETTERS = "JFMAMJJASOND"

_EXPIRY_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d-%B-%Y")

_DEFAULT_TIMEOUT = GROWW_HTTP_TIMEOUT
_DEFAULT_INTERVAL = 5

_HEADERS = GROWW_HEADERS

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)


# ── Small helpers ─────────────────────────────────────────────────────────────


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_expiry(expiry: str) -> datetime:
    for fmt in _EXPIRY_FORMATS:
        try:
            return datetime.strptime(expiry, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Unrecognised expiry {expiry!r}; expected YYYY-MM-DD or DD-Mon-YYYY"
    )


def build_groww_symbol(
    underlying: str,
    expiry: str,
    strike: float,
    option_type: str = "CE",
    monthly: bool = False,
) -> str:
    """Build Groww's contract id for an option.

    Args:
        underlying: e.g. ``"NIFTY"``.
        expiry: ``YYYY-MM-DD`` (Groww) or ``DD-Mon-YYYY``/``DD-MM-YYYY``.
        strike: strike price e.g. ``23000``.
        option_type: ``"CE"`` or ``"PE"``.
        monthly: ``True`` for the monthly contract (``NIFTY26OCT23000PE``),
            ``False`` for a weekly one (``NIFTY26O0623000PE``). Prefer
            :func:`find_groww_contract` when unsure - it reads the exact id.
    """
    dt = _parse_expiry(expiry)
    year = dt.strftime("%y")
    strike_i = int(round(float(strike)))
    if monthly:
        token = f"{year}{dt.strftime('%b').upper()}"
    else:
        token = f"{year}{_MONTH_LETTERS[dt.month - 1]}{dt.strftime('%d')}"
    return f"{underlying.upper()}{token}{strike_i}{option_type.upper()}"


# ── Models ────────────────────────────────────────────────────────────────────


@dataclass
class GrowwCandle:
    """A single Groww OHLCV candle."""

    timestamp: int = 0  # epoch seconds (UTC)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }

    def as_candle(self):
        """Convert to a :class:`dataspear.utils.yahoo.Candle` (for levels)."""
        from dataspear.utils.yahoo import Candle

        return Candle(
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


@dataclass
class GrowwChart:
    """Delayed intraday chart for an index or an option contract."""

    symbol: str = ""
    segment: str = "CASH"
    interval: int = _DEFAULT_INTERVAL
    source: str = "groww"
    close_price: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    candles: List[GrowwCandle] = field(default_factory=list)

    @property
    def last_price(self) -> float:
        return self.candles[-1].close if self.candles else 0.0

    @property
    def high(self) -> float:
        return max((c.high for c in self.candles), default=0.0)

    @property
    def low(self) -> float:
        return min((c.low for c in self.candles), default=0.0)

    @property
    def total_volume(self) -> int:
        return sum(c.volume for c in self.candles)

    def as_candles(self) -> list:
        """Return the series as ``dataspear.utils.yahoo.Candle`` objects."""
        return [c.as_candle() for c in self.candles]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "segment": self.segment,
            "interval": self.interval,
            "source": self.source,
            "close_price": self.close_price,
            "change": self.change,
            "change_pct": self.change_pct,
            "last_price": self.last_price,
            "high": self.high,
            "low": self.low,
            "total_volume": self.total_volume,
            "candles": [c.to_dict() for c in self.candles],
        }


@dataclass
class GrowwQuote:
    """One leg (CE or PE) of a Groww option strike."""

    contract_id: str = ""
    token: str = ""
    ltp: float = 0.0
    close: float = 0.0
    day_change: float = 0.0
    day_change_pct: float = 0.0
    oi: int = 0
    prev_oi: int = 0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    pop: float = 0.0
    markers: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "token": self.token,
            "ltp": self.ltp,
            "close": self.close,
            "day_change": self.day_change,
            "day_change_pct": self.day_change_pct,
            "oi": self.oi,
            "prev_oi": self.prev_oi,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "pop": self.pop,
            "markers": self.markers,
        }


@dataclass
class GrowwLiveQuote:
    """Parsed live price snapshot for one Groww contract."""

    contract_id: str = ""
    symbol: str = ""
    segment: str = ""
    ltp: float = 0.0
    close: float = 0.0
    day_change: float = 0.0
    day_change_pct: float = 0.0
    oi: int = 0
    prev_oi: int = 0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    pop: float = 0.0

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "symbol": self.symbol,
            "segment": self.segment,
            "ltp": self.ltp,
            "close": self.close,
            "day_change": self.day_change,
            "day_change_pct": self.day_change_pct,
            "oi": self.oi,
            "prev_oi": self.prev_oi,
            "iv": self.iv,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "pop": self.pop,
        }


@dataclass
class GrowwStrike:
    """A single strike row with its call and put legs."""

    strike: float = 0.0
    ce: GrowwQuote = field(default_factory=GrowwQuote)
    pe: GrowwQuote = field(default_factory=GrowwQuote)

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "ce": self.ce.to_dict(),
            "pe": self.pe.to_dict(),
        }


@dataclass
class GrowwOptionChain:
    """Parsed Groww option chain for one expiry."""

    underlying: str = ""
    spot: float = 0.0
    expiry: str = ""
    expiries: List[str] = field(default_factory=list)
    lot_size: int = 0
    freeze_qty: int = 0
    strikes: List[GrowwStrike] = field(default_factory=list)

    def atm_strike(self) -> float:
        if not self.strikes:
            return 0.0
        return min(self.strikes, key=lambda s: abs(s.strike - self.spot)).strike

    def to_dict(self) -> dict:
        return {
            "underlying": self.underlying,
            "spot": self.spot,
            "expiry": self.expiry,
            "expiries": self.expiries,
            "lot_size": self.lot_size,
            "freeze_qty": self.freeze_qty,
            "strikes": [s.to_dict() for s in self.strikes],
        }


# ── Parsing (pure) ────────────────────────────────────────────────────────────


def parse_candles(raw: Optional[dict]) -> List[GrowwCandle]:
    """Parse Groww's ``candles`` array into :class:`GrowwCandle` objects.

    Each row is ``[epoch_seconds, open, high, low, close, volume?]``.
    """
    rows = (raw or {}).get("candles") or []
    candles: List[GrowwCandle] = []
    for row in rows:
        try:
            ts = int(row[0])
            open_ = float(row[1])
            high = float(row[2])
            low = float(row[3])
            close = float(row[4])
        except (TypeError, ValueError, IndexError):
            continue
        volume = row[5] if len(row) > 5 and row[5] is not None else 0
        candles.append(
            GrowwCandle(
                timestamp=ts,
                open=round(open_, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=_to_int(volume),
            )
        )
    candles.sort(key=lambda c: c.timestamp)
    return candles


def parse_chart(raw: Optional[dict], symbol: str = "", segment: str = "CASH",
                interval: int = _DEFAULT_INTERVAL) -> GrowwChart:
    """Parse a raw Groww chart payload into a :class:`GrowwChart`."""
    return GrowwChart(
        symbol=symbol,
        segment=segment,
        interval=interval,
        close_price=_to_float((raw or {}).get("closingPrice")),
        change=_to_float((raw or {}).get("changeValue")),
        change_pct=_to_float((raw or {}).get("changePerc")),
        candles=parse_candles(raw),
    )


def parse_next_data(html: str) -> Optional[dict]:
    """Extract and decode the ``__NEXT_DATA__`` JSON blob from a Groww page."""
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return None
    import json

    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def _parse_quote(side: Optional[dict]) -> GrowwQuote:
    side = side or {}
    live = side.get("liveData") or {}
    greeks = side.get("greeks") or {}
    return GrowwQuote(
        contract_id=side.get("growwContractId") or "",
        token=str(side.get("token") or ""),
        ltp=_to_float(live.get("ltp")),
        close=_to_float(live.get("close")),
        day_change=_to_float(live.get("dayChange")),
        day_change_pct=_to_float(live.get("dayChangePerc")),
        oi=_to_int(live.get("oi")),
        prev_oi=_to_int(live.get("prevOI")),
        iv=_to_float(greeks.get("iv")),
        delta=_to_float(greeks.get("delta")),
        gamma=_to_float(greeks.get("gamma")),
        theta=_to_float(greeks.get("theta")),
        vega=_to_float(greeks.get("vega")),
        rho=_to_float(greeks.get("rho")),
        pop=_to_float(greeks.get("pop")),
        markers=list(side.get("markers") or []),
    )


def parse_option_chain(
    next_data: Optional[dict], underlying: str = ""
) -> GrowwOptionChain:
    """Parse a Groww ``__NEXT_DATA__`` payload into a :class:`GrowwOptionChain`."""
    data = ((next_data or {}).get("props") or {}).get("pageProps", {}).get("data", {})
    option_chain = data.get("optionChain") or {}
    aggregated = option_chain.get("aggregatedDetails") or {}
    company = data.get("company") or {}

    contracts = option_chain.get("optionContracts") or []
    strikes: List[GrowwStrike] = []
    for item in contracts:
        # Groww reports strikes in paise (2005000 -> 20050).
        strike = _to_float(item.get("strikePrice"))
        if strike > 100000:
            strike = round(strike / 100.0, 2)
        strikes.append(
            GrowwStrike(
                strike=strike,
                ce=_parse_quote(item.get("ce")),
                pe=_parse_quote(item.get("pe")),
            )
        )
    strikes.sort(key=lambda s: s.strike)

    return GrowwOptionChain(
        underlying=underlying or company.get("symbol") or company.get("name") or "",
        spot=_to_float((company.get("liveData") or {}).get("ltp")),
        expiry=aggregated.get("currentExpiry") or "",
        expiries=list(aggregated.get("expiryDates") or []),
        lot_size=_to_int(aggregated.get("lotSize")),
        freeze_qty=_to_int(aggregated.get("freezeQty")),
        strikes=strikes,
    )


# ── Async fetch helpers ───────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(_time.time() * 1000)


async def _get_json(url: str, params: Optional[dict] = None) -> dict:
    return await get_json(url, params=params, headers=_HEADERS, timeout=_DEFAULT_TIMEOUT)


async def _get_text(url: str, params: Optional[dict] = None) -> str:
    return await get_text(url, params=params, headers=_HEADERS, timeout=_DEFAULT_TIMEOUT)


async def fetch_groww_candles(
    symbol: str = "NIFTY",
    segment: str = "CASH",
    interval: int = _DEFAULT_INTERVAL,
    data_range: int = 60,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> GrowwChart:
    """Fetch a delayed intraday chart for an index (``CASH``) or option (``FNO``).

    Args:
        symbol: ``NIFTY`` for CASH, or a Groww contract id for FNO.
        segment: ``"CASH"`` or ``"FNO"``.
        interval: candle size in minutes (default 5).
        data_range: minutes to look back when no explicit window is given.
        start_time/end_time: explicit epoch **milliseconds** window.
    """
    end_ms = end_time if end_time is not None else _now_ms()
    start_ms = (
        start_time
        if start_time is not None
        else end_ms - int(data_range) * 60 * 1000
    )
    url = CHART_URL.format(segment=segment, symbol=symbol)
    try:
        raw = await _get_json(
            url,
            params={
                "endTimeInMillis": end_ms,
                "intervalInMinutes": interval,
                "startTimeInMillis": start_ms,
            },
        )
    except httpx.HTTPError as exc:
        log.warning("Groww chart fetch failed for %s: %s", symbol, exc)
        raise
    return parse_chart(raw, symbol=symbol, segment=segment, interval=interval)


async def fetch_groww_option_chart(
    symbol: str,
    interval: int = _DEFAULT_INTERVAL,
    data_range: int = 60,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> GrowwChart:
    """Fetch the intraday chart for a Groww option contract id (segment FNO)."""
    return await fetch_groww_candles(
        symbol=symbol,
        segment="FNO",
        interval=interval,
        data_range=data_range,
        start_time=start_time,
        end_time=end_time,
    )


async def fetch_groww_expiries(underlying: str = "NIFTY") -> List[str]:
    """List available expiries (``YYYY-MM-DD``) for ``underlying``."""
    chain = await fetch_groww_option_chain(underlying)
    return chain.expiries


async def fetch_groww_option_chain(
    underlying: str = "NIFTY", expiry: Optional[str] = None
) -> GrowwOptionChain:
    """Fetch and parse the Groww option chain for ``underlying``.

    Args:
        underlying: e.g. ``"NIFTY"``.
        expiry: ``YYYY-MM-DD``; defaults to Groww's current expiry.
    """
    params = {"expiry": expiry} if expiry else None
    url = OPTION_CHAIN_URL.format(underlying=underlying.lower())
    html = await _get_text(url, params=params)
    next_data = parse_next_data(html)
    if next_data is None:
        raise RuntimeError(f"Could not parse Groww option-chain page: {url}")
    return parse_option_chain(next_data, underlying=underlying.upper())


def _parse_live_payload(symbol: str, payload: dict) -> GrowwLiveQuote:
    """Parse a raw live-price JSON payload into a :class:`GrowwLiveQuote`."""
    live = (payload or {}).get("data") or (payload or {}).get("liveData") or {}
    greeks = (payload or {}).get("greeks") or {}
    return GrowwLiveQuote(
        contract_id=payload.get("growwContractId") or symbol,
        symbol=payload.get("symbol") or symbol,
        segment=payload.get("segment") or "FNO",
        ltp=_to_float(live.get("ltp") if isinstance(live, dict) else None),
        close=_to_float(live.get("close") if isinstance(live, dict) else None),
        day_change=_to_float(live.get("dayChange") if isinstance(live, dict) else None),
        day_change_pct=_to_float(live.get("dayChangePerc") if isinstance(live, dict) else None),
        oi=_to_int(live.get("oi") if isinstance(live, dict) else None),
        prev_oi=_to_int(live.get("prevOI") if isinstance(live, dict) else None),
        iv=_to_float(greeks.get("iv") if isinstance(greeks, dict) else None),
        delta=_to_float(greeks.get("delta") if isinstance(greeks, dict) else None),
        gamma=_to_float(greeks.get("gamma") if isinstance(greeks, dict) else None),
        theta=_to_float(greeks.get("theta") if isinstance(greeks, dict) else None),
        vega=_to_float(greeks.get("vega") if isinstance(greeks, dict) else None),
        rho=_to_float(greeks.get("rho") if isinstance(greeks, dict) else None),
        pop=_to_float(greeks.get("pop") if isinstance(greeks, dict) else None),
    )


async def fetch_groww_live_price(
    symbol: str, segment: str = "FNO", exchange: str = "NSE"
) -> GrowwLiveQuote:
    """Fetch and parse the live price snapshot for one Groww contract.

    Returns a :class:`GrowwLiveQuote` (never a raw dict) so consumers get a
    consistent typed model. On HTTP failure returns a zeroed quote.
    """
    url = LIVE_PRICE_URL.format(exchange=exchange, segment=segment, symbol=symbol)
    try:
        payload = await _get_json(url)
        return _parse_live_payload(symbol, payload)
    except httpx.HTTPError as exc:
        log.warning("Groww live price fetch failed for %s: %s", symbol, exc)
        return GrowwLiveQuote(contract_id=symbol, symbol=symbol, segment=segment)


async def find_groww_contract(
    underlying: str, expiry: str, strike: float, option_type: str = "CE"
) -> str:
    """Resolve the exact Groww ``contract_id`` for one strike/expiry/type.

    More reliable than :func:`build_groww_symbol` because it reads the id Groww
    itself reports (weekly vs monthly, exact strike formatting).
    """
    chain = await fetch_groww_option_chain(underlying, expiry=expiry)
    target = int(round(float(strike)))
    for row in chain.strikes:
        if int(round(row.strike)) != target:
            continue
        quote = row.ce if option_type.upper() == "CE" else row.pe
        if quote.contract_id:
            return quote.contract_id
        break
    raise ValueError(
        f"No Groww contract for {underlying} {expiry} {strike} {option_type}"
    )


def _chart_from_nse(nse_chart: Any, symbol: str, interval: int) -> GrowwChart:
    """Adapt an NSE :class:`OptionChart` into a :class:`GrowwChart`.

    NSE points carry only a price, so OHLC collapse onto that price.
    """
    epoch = datetime(1970, 1, 1, tzinfo=IST)

    def epoch_seconds(timestamp: datetime) -> int:
        """Convert timestamps without relying on Windows' C-runtime epoch."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=IST)
        return int((timestamp - epoch).total_seconds())

    candles = [
        GrowwCandle(
            timestamp=epoch_seconds(p.timestamp),
            open=p.price,
            high=p.price,
            low=p.price,
            close=p.price,
            volume=p.volume,
        )
        for p in getattr(nse_chart, "points", [])
    ]
    return GrowwChart(
        symbol=symbol,
        segment="FNO",
        interval=interval,
        source="nse",
        close_price=getattr(nse_chart, "close_price", 0.0),
        candles=candles,
    )


async def get_groww_option_chart(
    expiry: str,
    strike: float,
    option_type: str = "CE",
    underlying: str = "NIFTY",
    interval: int = _DEFAULT_INTERVAL,
    data_range: int = 60,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    fallback_nse: bool = True,
) -> GrowwChart:
    """Fetch the intraday chart for one option leg, resolving its Groww id.

    Groww's delayed chart service carries no FNO candles (verified: it returns
    an empty ``candles`` array for options and futures alike), so when the Groww
    series is empty and ``fallback_nse`` is set, the NSE option chart is used
    instead and ``source`` is set to ``"nse"``. Set ``fallback_nse=False`` to
    get Groww's (possibly empty) series only.
    """
    symbol = await find_groww_contract(underlying, expiry, strike, option_type)
    chart = await fetch_groww_option_chart(
        symbol,
        interval=interval,
        data_range=data_range,
        start_time=start_time,
        end_time=end_time,
    )
    if chart.candles or not fallback_nse:
        return chart

    from dataspear.nse.option_chart import fetch_option_chart

    log.debug("Groww returned no FNO candles for %s; falling back to NSE", symbol)
    nse_chart = await fetch_option_chart(expiry, strike, option_type)
    return _chart_from_nse(nse_chart, symbol, interval)


async def get_groww_levels(
    underlying: str = "NIFTY",
    interval: int = _DEFAULT_INTERVAL,
    data_range: int = 60,
    daily_range: int = 90,
    step: float = 50.0,
):
    """Detect price levels from Groww index candles.

    Fetches an intraday (default 5m) and a daily series and feeds both through
    :func:`dataspear.nse.levels.detect_levels`, returning a ``LevelAnalysis``.
    The daily series is best-effort: if Groww returns nothing for it, the
    intraday series is used alone.
    """
    from dataspear.nse.levels import detect_levels

    intraday = await fetch_groww_candles(
        symbol=underlying, segment="CASH", interval=interval, data_range=data_range
    )
    candle_sets = [intraday.as_candles()]
    try:
        # data_range is in minutes, so a day of lookback needs *1440.
        daily = await fetch_groww_candles(
            symbol=underlying,
            segment="CASH",
            interval=1440,
            data_range=daily_range * 1440,
        )
        if daily.candles:
            candle_sets.append(daily.as_candles())
    except httpx.HTTPError as exc:  # noqa: BLE001 - daily is optional
        log.debug("Groww daily candle fetch failed for %s: %s", underlying, exc)
    return detect_levels(candle_sets, step=step)


# ── Convenience aliases (mirror the NSE public names) ─────────────────────────


async def get_groww_expiries(underlying: str = "NIFTY") -> List[str]:
    """Alias for :func:`fetch_groww_expiries`."""
    return await fetch_groww_expiries(underlying)


async def get_groww_option_chain(
    underlying: str = "NIFTY", expiry: Optional[str] = None
) -> GrowwOptionChain:
    """Alias for :func:`fetch_groww_option_chain`."""
    return await fetch_groww_option_chain(underlying, expiry=expiry)
