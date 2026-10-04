"""Request objects ("specs") that :class:`dataspear.core.Core` can fetch.

A spec describes *what* to fetch and nothing about *how*:

* ``provider``       - which transport/base URL the core must use
* ``relative_url()`` - the path + query string, relative to that base URL
* ``parse(response)``- turns the raw HTTP response into the module's model

The core joins ``base_url + relative_url``, performs the HTTP request with the
right transport (plain HTTP, cookie-managed NSE session, ...), and returns
``spec.parse(response)``.  Specs that need several requests (option charts,
price levels) are *composite*: they override :meth:`RequestSpec.execute` and
fetch their parts through the same core.

    chart = await core.fetch(IndexSpec(suffix="NIFTY", interval=5, data_range=60))
    chain = await core.fetch(GrowwOptionChainSpec("NIFTY", expiry="2026-10-08"))
    lvls  = await core.fetch(LevelsSpec.groww("NIFTY"))
"""

from __future__ import annotations

import time
from copy import copy
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional, Sequence
from urllib.parse import quote, quote_plus, urlencode

from dataspear.base import CompositeSpec, RequestSpec
from dataspear.errors import InvalidParametersError
from dataspear.utils.validation import ConnectionType, IndexRequestParameters

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from dataspear.core import Core

__all__ = [
    "RequestSpec",
    "CompositeSpec",
    "IndexSpec",
    "GrowwChartSpec",
    "GrowwOptionChainSpec",
    "GrowwLivePriceSpec",
    "GrowwOptionChartSpec",
    "NseOptionChainSpec",
    "NseExpirySpec",
    "NseOptionChartSpec",
    "YahooCandlesSpec",
    "YahooQuoteSpec",
    "NewsSpec",
    "LevelsSpec",
    "as_spec",
]


def _query(params: dict[str, Any]) -> str:
    """``?a=1&b=2`` from non-None params (empty string when there are none)."""
    clean = {k: v for k, v in params.items() if v is not None}
    return f"?{urlencode(clean)}" if clean else ""


# ── index route (original DataConnection use case) ───────────────────────────


class IndexSpec(RequestSpec):
    """Delayed index candles from the configured Groww index route.

    Wraps :class:`IndexRequestParameters`; build it from keyword arguments or
    pass existing parameters with ``IndexSpec(params=...)``.  ``Live`` mode
    resolves its time window at the moment the URL is built.
    """

    provider = "index"

    def __init__(
        self,
        suffix: Optional[str] = None,
        interval: int = 5,
        data_range: int = 60,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        connection_type: Optional[ConnectionType] = None,
        *,
        params: Optional[IndexRequestParameters] = None,
        raw: bool = False,
    ) -> None:
        if params is None:
            if connection_type is None:
                connection_type = (
                    ConnectionType.History
                    if start_time is not None and end_time is not None
                    else ConnectionType.Live
                )
            try:
                params = IndexRequestParameters(
                    suffix=suffix, interval=interval, data_range=data_range,
                    start_time=start_time, end_time=end_time,
                    connection_type=connection_type,
                )
            except ValueError as exc:
                raise InvalidParametersError(str(exc)) from exc
        self.params = params
        self.raw = raw

    def _resolved(self) -> IndexRequestParameters:
        params = copy(self.params)
        if params.connection_type == ConnectionType.Live:
            now_ms = int(time.time() * 1000)
            params.start_time = now_ms - params.data_range * 60 * 1000
            params.end_time = now_ms
        try:
            params.validate()
        except ValueError as exc:
            raise InvalidParametersError(str(exc)) from exc
        return params

    def relative_url(self) -> str:
        from dataspear.utils.url import URL

        p = self._resolved()
        return (
            f"{URL._api_index_route()}{p.suffix}"
            f"?endTimeInMillis={p.end_time}&intervalInMinutes={p.interval}"
            f"&startTimeInMillis={p.start_time}"
        )

    def parse(self, response: "httpx.Response") -> Any:
        payload = response.json()
        if self.raw:
            return payload
        from dataspear.groww import parse_chart

        return parse_chart(
            payload, symbol=str(self.params.suffix), segment="CASH",
            interval=self.params.interval,
        )


# ── Groww ────────────────────────────────────────────────────────────────────


class GrowwChartSpec(RequestSpec):
    """Delayed Groww chart for an index (``CASH``) or an option contract id (``FNO``)."""

    provider = "groww"

    def __init__(
        self,
        symbol: str = "NIFTY",
        segment: str = "CASH",
        interval: int = 5,
        data_range: int = 60,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> None:
        self.symbol = symbol
        self.segment = segment
        self.interval = interval
        self.data_range = data_range
        self.start_time = start_time
        self.end_time = end_time

    def relative_url(self) -> str:
        end_ms = self.end_time if self.end_time is not None else int(time.time() * 1000)
        start_ms = (
            self.start_time
            if self.start_time is not None
            else end_ms - int(self.data_range) * 60 * 1000
        )
        return (
            "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/"
            f"{quote(self.segment, safe='')}/{quote(self.symbol, safe='')}"
            + _query({
                "endTimeInMillis": end_ms,
                "intervalInMinutes": self.interval,
                "startTimeInMillis": start_ms,
            })
        )

    def parse(self, response: "httpx.Response") -> Any:
        from dataspear.groww import parse_chart

        return parse_chart(
            response.json(), symbol=self.symbol, segment=self.segment, interval=self.interval
        )


class GrowwOptionChainSpec(RequestSpec):
    """Groww option chain page for an underlying (``expiry`` is ``YYYY-MM-DD``)."""

    provider = "groww"

    def __init__(self, underlying: str = "NIFTY", expiry: Optional[str] = None) -> None:
        self.underlying = underlying.upper()
        self.expiry = expiry

    def relative_url(self) -> str:
        return f"/options/{quote(self.underlying.lower(), safe='')}" + _query(
            {"expiry": self.expiry}
        )

    def parse(self, response: "httpx.Response") -> Any:
        from dataspear.groww import parse_next_data, parse_option_chain

        next_data = parse_next_data(response.text)
        if next_data is None:
            raise RuntimeError(f"Could not parse Groww option-chain page: {self.relative_url()}")
        return parse_option_chain(next_data, underlying=self.underlying)


class GrowwLivePriceSpec(RequestSpec):
    """Live price and greeks snapshot for one Groww contract id."""

    provider = "groww"

    def __init__(self, symbol: str, segment: str = "FNO", exchange: str = "NSE") -> None:
        self.symbol = symbol
        self.segment = segment
        self.exchange = exchange

    def relative_url(self) -> str:
        return (
            "/v1/api/stocks_fo_data/v1/tr_live_prices/exchange/"
            f"{quote(self.exchange, safe='')}/segment/{quote(self.segment, safe='')}"
            f"/{quote(self.symbol, safe='')}/latest"
        )

    def parse(self, response: "httpx.Response") -> Any:
        from dataspear.groww import _parse_live_payload

        return _parse_live_payload(self.symbol, response.json())


class GrowwOptionChartSpec(CompositeSpec):
    """Intraday chart for one option leg, resolved from strike/expiry/type.

    Fetches the option chain to find Groww's contract id, then the FNO chart.
    Groww carries no FNO candles, so by default an empty series falls back to
    the NSE chart (``source == "nse"`` on the result).
    """

    def __init__(
        self,
        expiry: str,
        strike: float,
        option_type: str = "CE",
        underlying: str = "NIFTY",
        interval: int = 5,
        data_range: int = 60,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        fallback_nse: bool = True,
    ) -> None:
        self.expiry = expiry
        self.strike = strike
        self.option_type = option_type
        self.underlying = underlying.upper()
        self.interval = interval
        self.data_range = data_range
        self.start_time = start_time
        self.end_time = end_time
        self.fallback_nse = fallback_nse

    async def execute(self, core: "Core") -> Any:
        from dataspear.groww import _chart_from_nse, contract_from_chain

        chain = await core.fetch(GrowwOptionChainSpec(self.underlying, self.expiry))
        symbol = contract_from_chain(
            chain, self.strike, self.option_type,
            underlying=self.underlying, expiry=self.expiry,
        )
        chart = await core.fetch(
            GrowwChartSpec(
                symbol, "FNO", self.interval, self.data_range, self.start_time, self.end_time
            )
        )
        if chart.candles or not self.fallback_nse:
            return chart
        nse_chart = await core.fetch(
            NseOptionChartSpec(self.expiry, self.strike, self.option_type)
        )
        return _chart_from_nse(nse_chart, symbol, self.interval)


# ── NSE ──────────────────────────────────────────────────────────────────────


class NseOptionChainSpec(RequestSpec):
    """NSE NIFTY option chain (``expiry`` as ``DD-Mon-YYYY``; ``atm_range`` trims strikes)."""

    provider = "nse"

    def __init__(
        self, expiry: Optional[str] = None, atm_range: Optional[int] = None, raw: bool = False
    ) -> None:
        self.expiry = expiry
        self.atm_range = atm_range
        self.raw = raw

    def relative_url(self) -> str:
        url = "/api/option-chain-v3?type=Indices&symbol=NIFTY"
        if self.expiry:
            url += f"&expiry={quote_plus(self.expiry)}"
        return url

    def parse(self, response: "httpx.Response") -> Any:
        data = response.json()
        if self.raw:
            return data
        from dataspear.nse.option_chain import parse_option_chain

        chain = parse_option_chain(data)
        return chain.filter_atm(self.atm_range) if self.atm_range else chain


class NseExpirySpec(CompositeSpec):
    """Available NIFTY expiries: contract-info endpoint first, then the chain itself."""

    async def execute(self, core: "Core") -> list[str]:
        from dataspear.nse.option_chain import expiries_from_chain

        try:
            info = await core.get(_UrlSpec("nse", "/api/option-chain-contract-info?symbol=NIFTY"))
            dates = info.json().get("expiryDates", [])
            if dates:
                return list(dates)
        except Exception:  # noqa: BLE001 - fall back to the chain
            pass
        return expiries_from_chain(await core.fetch(NseOptionChainSpec(raw=True)))


class NseOptionChartSpec(RequestSpec):
    """Intraday price/volume series for one NSE option contract."""

    provider = "nse"

    def __init__(self, expiry: str, strike: float, option_type: str = "CE") -> None:
        self.expiry = expiry
        self.strike = strike
        self.option_type = option_type

    @property
    def identifier(self) -> str:
        from dataspear.nse.option_chart import build_identifier

        return build_identifier(self.expiry, self.strike, self.option_type)

    def relative_url(self) -> str:
        return f"/api/chart-databyindex?index={quote_plus(self.identifier)}"

    def parse(self, response: "httpx.Response") -> Any:
        from dataspear.nse.option_chart import parse_chart_data

        return parse_chart_data(
            response.json(), identifier=self.identifier, expiry=self.expiry,
            strike=self.strike, option_type=self.option_type,
        )


# ── Yahoo ────────────────────────────────────────────────────────────────────


class _YahooSpec(RequestSpec, ABC):
    """Shared URL for Yahoo chart requests; subclasses decide how to parse."""

    provider = "yahoo"

    def __init__(self, ticker: str = "^NSEI", range_: str = "5d", interval: str = "1d") -> None:
        self.ticker = ticker
        self.range_ = range_
        self.interval = interval

    def relative_url(self) -> str:
        return f"/v8/finance/chart/{quote(self.ticker, safe='^')}" + _query(
            {"range": self.range_, "interval": self.interval, "includePrePost": "false"}
        )

    @abstractmethod
    def parse(self, response: "httpx.Response") -> Any:
        """Turn the chart payload into candles, a quote, ..."""


class YahooCandlesSpec(_YahooSpec):
    """Parsed OHLCV candles for a Yahoo ticker."""

    def parse(self, response: "httpx.Response") -> Any:
        from dataspear.utils.yahoo import parse_chart

        return parse_chart(response.json())[1]


class YahooQuoteSpec(_YahooSpec):
    """``{price, prev_close, change, change_pct}`` for a Yahoo ticker."""

    def __init__(self, ticker: str = "^NSEI", range_: str = "1d", interval: str = "1d") -> None:
        super().__init__(ticker, range_, interval)

    def parse(self, response: "httpx.Response") -> Any:
        from dataspear.utils.yahoo import quote_from_payload

        return quote_from_payload(response.json())


# ── News ─────────────────────────────────────────────────────────────────────


class NewsSpec(RequestSpec):
    """Scored Google News RSS headlines for a raw query or a named category."""

    provider = "news"

    def __init__(
        self,
        query: Optional[str] = None,
        category: str = "market",
        days: int = 1,
        max_results: int = 8,
        fetch_full_content: bool = False,
    ) -> None:
        from dataspear.news import QUERIES

        self.category = category
        self.query = query or QUERIES.get(category)
        if not self.query:
            raise InvalidParametersError(f"Unknown news category: {category!r}.")
        self.days = days
        self.max_results = max_results
        self.fetch_full_content = fetch_full_content

    def relative_url(self) -> str:
        return f"/rss/search?q={quote_plus(self.query)}&hl=en-IN&gl=IN&ceid=IN:en"

    def parse(self, response: "httpx.Response") -> Any:
        from dataspear.news import _is_recent, parse_rss

        articles = parse_rss(response.text, category=self.category, max_results=self.max_results)
        return [a for a in articles if _is_recent(a.published, self.days)]

    async def execute(self, core: "Core") -> Any:
        articles = await super().execute(core)
        if self.fetch_full_content:
            from dataspear.news import fetch_article_content

            for article in articles:
                article.full_content = await fetch_article_content(article.url)
        return articles


# ── Levels (composite) ───────────────────────────────────────────────────────


class LevelsSpec(CompositeSpec):
    """Support/resistance and stop-hunt levels from one or more candle sources.

    ``sources`` are any chart specs whose result holds candles (a Groww chart,
    a Yahoo candle list, ...).  Every source is fetched through the core and
    handed to :func:`dataspear.nse.levels.detect_levels`.  ``optional`` sources
    (e.g. the daily series) are skipped when they fail or come back empty.
    """

    def __init__(
        self,
        sources: Sequence[RequestSpec],
        optional: Sequence[RequestSpec] = (),
        step: float = 50.0,
    ) -> None:
        if not sources:
            raise InvalidParametersError("LevelsSpec needs at least one candle source.")
        self.sources = list(sources)
        self.optional = list(optional)
        self.step = step

    @classmethod
    def groww(
        cls,
        underlying: str = "NIFTY",
        interval: int = 5,
        data_range: int = 60,
        daily_range: int = 90,
        step: float = 50.0,
    ) -> "LevelsSpec":
        """Intraday plus daily Groww index candles (what ``get_groww_levels`` uses)."""
        return cls(
            sources=[GrowwChartSpec(underlying, "CASH", interval, data_range)],
            # data_range is in minutes, so a day of lookback needs *1440.
            optional=[GrowwChartSpec(underlying, "CASH", 1440, daily_range * 1440)],
            step=step,
        )

    @classmethod
    def yahoo(
        cls, ticker: str = "^NSEI", range_: str = "1mo", interval: str = "30m", step: float = 50.0
    ) -> "LevelsSpec":
        """Levels from Yahoo candles."""
        return cls(sources=[YahooCandlesSpec(ticker, range_, interval)], step=step)

    @staticmethod
    def _candles(result: Any) -> list:
        if hasattr(result, "as_candles"):
            return list(result.as_candles())
        if isinstance(result, tuple) and len(result) == 2:
            return list(result[1])
        return list(result or [])

    async def execute(self, core: "Core") -> Any:
        import asyncio

        from dataspear.nse.levels import detect_levels

        required = await asyncio.gather(*(core.fetch(s) for s in self.sources))
        extra = await asyncio.gather(
            *(core.fetch(s) for s in self.optional), return_exceptions=True
        )
        candle_sets = [self._candles(r) for r in required]
        candle_sets += [
            c for c in (self._candles(r) for r in extra if not isinstance(r, BaseException)) if c
        ]
        return detect_levels(candle_sets, step=self.step)


# ── helpers ──────────────────────────────────────────────────────────────────


class _UrlSpec(RequestSpec):
    """Internal: an ad-hoc relative URL on a provider (no parsing)."""

    def __init__(self, provider: str, relative: str) -> None:
        self._provider = provider
        self._relative = relative

    @property
    def provider(self) -> str:  # type: ignore[override]
        return self._provider

    def relative_url(self) -> str:
        return self._relative


def as_spec(obj: Any) -> RequestSpec:
    """Turn the legacy index objects into a spec; specs pass through unchanged.

    Accepts a :class:`RequestSpec`, an :class:`IndexRequestParameters`, or a
    legacy ``DataConnection`` / ``IndexDataConnection`` (its parameters are used).
    """
    if isinstance(obj, RequestSpec):
        return obj
    if isinstance(obj, IndexRequestParameters):
        return IndexSpec(params=obj)
    params = getattr(obj, "params", None)
    if isinstance(params, IndexRequestParameters):
        return IndexSpec(params=params)
    if obj.__class__.__name__ in ("DataConnection", "IndexDataConnection"):
        raise InvalidParametersError("The connection has no parameters set (`params` is None).")
    raise InvalidParametersError(f"Cannot fetch {type(obj).__name__}: not a request spec.")
