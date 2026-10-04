"""Core request handler, AI tool discovery catalog and legacy connection exports.

:class:`Core` is the one place that talks to the network.  It is *given request
objects* (see :mod:`dataspear.specs`) - an index request, a Groww option chain,
an NSE option chart, a levels request, ... - and for each one it

1. looks up the transport for the object's ``provider`` (base URL, headers,
   cookie session),
2. joins the base URL with the object's *relative* URL,
3. fetches it, and
4. hands the response back to the object to parse.

::

    async with Core.with_defaults() as core:
        chart = await core.fetch(IndexSpec(suffix="NIFTY", interval=5))
        chain = await core.fetch(GrowwOptionChainSpec("NIFTY", expiry="2026-10-08"))
        lvls = await core.fetch(LevelsSpec.groww("NIFTY"))
        out = await core.fetch_many([NseOptionChainSpec(), YahooQuoteSpec("^INDIAVIX")])

The legacy ``IndexRequestParameters`` / ``DataConnection`` objects are accepted
directly.  Provider connection implementations live in
:mod:`dataspear.connections`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import inspect
import time
from datetime import date, datetime
from typing import Any, Callable, Iterable, Mapping, Optional, Union

import httpx

# NOTE: dict, list are builtins in Python 3.9+; do not import from typing.

from dataspear.connections import DataConnection, IndexDataConnection
from dataspear.base import Transport
from dataspear.errors import (
    DataSpearError,
    InvalidParametersError,
    UnknownProviderError,
)
from dataspear.settings import (
    DEFAULT_BASE_URL,
    GOOGLE_NEWS_BASE_URL,
    GROWW_BASE_URL,
    GROWW_HEADERS,
    GROWW_HTTP_TIMEOUT,
    JSON_HEADERS,
    NEWS_HEADERS,
    YAHOO_BASE_URL,
)
from dataspear.specs import RequestSpec, as_spec
from dataspear.transports import HttpTransport, NseTransport

__all__ = [
    "Core",
    "Result",
    "Transport",
    "HttpTransport",
    "NseTransport",
    "ai_tool_tip",
    "DataConnection",
    "IndexDataConnection",
    "DataSpearError",
    "UnknownProviderError",
    "InvalidParametersError",
]


# ── result envelope ──────────────────────────────────────────────────────────


def _jsonable(value: Any, _depth: int = 0) -> Any:
    """Best-effort conversion of parsed results into JSON-friendly data."""
    if _depth > 12 or value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict(), _depth + 1)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value), _depth + 1)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v, _depth + 1) for v in value]
    return str(value)


@dataclasses.dataclass
class Result:
    """Outcome of :meth:`Core.try_fetch` / :meth:`Core.fetch_many` (never raises)."""

    spec: str
    ok: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    elapsed_ms: float = 0.0

    def unwrap(self) -> Any:
        """Return ``data``, or raise :class:`DataSpearError` describing the failure."""
        if not self.ok:
            raise DataSpearError(f"{self.spec} failed: {self.error_type}: {self.error}")
        return self.data

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec,
            "ok": self.ok,
            "data": _jsonable(self.data),
            "error": self.error,
            "error_type": self.error_type,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


# ── the core ─────────────────────────────────────────────────────────────────


class Core:
    """Fetches request objects through per-provider transports.

    Args:
        transports: optional ``{provider: Transport}`` to register immediately.
        timeout: default per-fetch timeout in seconds (``None`` disables it).
        max_concurrency: cap on simultaneous fetches inside :meth:`fetch_many`.
    """

    def __init__(
        self,
        transports: Optional[Mapping[str, Transport]] = None,
        *,
        timeout: Optional[float] = 30.0,
        max_concurrency: int = 10,
    ) -> None:
        self.timeout = timeout
        self.max_concurrency = max(1, max_concurrency)
        self._transports: dict[str, Transport] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
        for name, transport in (transports or {}).items():
            self.register_transport(name, transport)

    @classmethod
    def with_defaults(cls, **kwargs: Any) -> "Core":
        """A Core wired for the index route, Groww, NSE, Yahoo and Google News."""
        from dataspear.utils.url import URL

        core = cls(**kwargs)
        # The index route honours config.load_env() at request time.
        core.register_transport("index", HttpTransport(URL._base_url, JSON_HEADERS))
        core.register_transport(
            "groww", HttpTransport(GROWW_BASE_URL, GROWW_HEADERS, GROWW_HTTP_TIMEOUT)
        )
        core.register_transport("nse", NseTransport())
        core.register_transport("yahoo", HttpTransport(YAHOO_BASE_URL, JSON_HEADERS))
        core.register_transport("news", HttpTransport(GOOGLE_NEWS_BASE_URL, NEWS_HEADERS))
        return core

    # -- transports ----------------------------------------------------------

    def register_transport(
        self, provider: str, transport: Transport, *, replace: bool = False
    ) -> Transport:
        """Make ``provider`` reachable.  Any spec with that ``provider`` will use it."""
        if not isinstance(transport, Transport):
            raise TypeError(f"{type(transport).__name__} must subclass Transport.")
        if not provider:
            raise ValueError("A transport needs a provider name.")
        if provider in self._transports and not replace:
            raise ValueError(f"Transport {provider!r} already registered (use replace=True).")
        self._transports[provider] = transport
        return transport

    @property
    def providers(self) -> list[str]:
        return sorted(self._transports)

    def transport(self, provider: str) -> Transport:
        try:
            return self._transports[provider]
        except KeyError:
            raise UnknownProviderError(
                f"No transport for provider {provider!r}. "
                f"Registered: {', '.join(self.providers) or 'none'}"
            ) from None

    # -- fetching ------------------------------------------------------------

    def url_for(self, spec: Any) -> str:
        """The absolute URL the core would request for a (non-composite) spec."""
        spec = as_spec(spec)
        relative = spec.relative_url()  # first: composites explain themselves here
        return self.transport(spec.provider).url(relative)

    async def get(self, spec: Any) -> httpx.Response:
        """Fetch a single spec's URL and return the raw HTTP response (no parsing)."""
        spec = as_spec(spec)
        relative = spec.relative_url()
        transport = self.transport(spec.provider)
        return await transport.get(transport.url(relative))

    async def fetch(self, spec: Any, *, timeout: Optional[float] = None) -> Any:
        """Fetch ``spec`` and return its parsed result, raising on any failure.

        ``spec`` may be any :class:`RequestSpec`, ``IndexRequestParameters`` or a
        legacy ``DataConnection``/``IndexDataConnection``.
        """
        spec = as_spec(spec)
        limit = timeout if timeout is not None else self.timeout
        work = spec.execute(self)
        if limit is None:
            return await work
        try:
            return await asyncio.wait_for(work, limit)
        except asyncio.TimeoutError:
            raise TimeoutError(f"{type(spec).__name__} timed out after {limit:g}s") from None

    async def try_fetch(self, spec: Any, *, timeout: Optional[float] = None) -> Result:
        """Like :meth:`fetch`, but failures come back as ``Result(ok=False)``."""
        name = type(spec).__name__
        started = time.perf_counter()
        try:
            data = await self.fetch(spec, timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the envelope is the contract
            return Result(
                name, False, error=str(exc) or type(exc).__name__,
                error_type=type(exc).__name__,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
        return Result(name, True, data=data, elapsed_ms=(time.perf_counter() - started) * 1000)

    async def fetch_many(self, specs: Iterable[Any]) -> list[Result]:
        """Fetch many specs concurrently (any provider mix); order is preserved."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)

        async def one(spec: Any) -> Result:
            async with self._semaphore:
                return await self.try_fetch(spec)

        return list(await asyncio.gather(*(one(s) for s in specs)))

    # -- lifecycle -----------------------------------------------------------

    async def aclose(self) -> None:
        await asyncio.gather(
            *(t.aclose() for t in self._transports.values()), return_exceptions=True
        )

    async def __aenter__(self) -> "Core":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()


# Public tool registry: every named capability in dataspear, by section.
# References are resolved lazily by ``ai_tool_tip``.  This keeps the core free
# of imports that would otherwise create circular dependencies with
# ``dataspear.nse`` and the other convenience modules.

_TOOL_REGISTRY: dict[str, tuple[str, str, Callable[..., Any] | None]] = {}


def _register(
    category: str, name: str, description: str, fn: Callable[..., Any] | None = None
) -> None:
    _TOOL_REGISTRY[name] = (category, description, fn)


_TOOL_MODULES = {
    "option_chain": "dataspear.nse",
    "oi": "dataspear.nse",
    "vix": "dataspear.nse",
    "levels": "dataspear.nse",
    "chart": "dataspear.nse",
    "extras": "dataspear.nse",
    "time": "dataspear.nse",
    "regime": "dataspear.nse",
    "scanner": "dataspear.nse",
    "context": "dataspear.nse",
    "session": "dataspear.nse",
    "groww": "dataspear.groww",
    "news": "dataspear.news",
    "yahoo": "dataspear.utils.yahoo",
    "http": "dataspear.utils.request_handler",
    "time_utils": "dataspear.utils.time",
    "validation": "dataspear.utils.validation",
    "config": "dataspear.settings",
    "core": "dataspear.core",
    "specs": "dataspear.specs",
}


def _resolve_tool(category: str, name: str) -> Callable[..., Any] | None:
    """Return the callable registered under ``category``/``name``, if any."""
    if name == "URL.get_url":
        from dataspear.utils.url import URL

        return URL.get_url

    if name in {"RequestHandler", "IndexRequestParameters", "ConnectionType"}:
        module_name = (
            "dataspear.utils.request_handler"
            if name == "RequestHandler"
            else "dataspear.utils.validation"
        )
    elif name in {"DataConnection", "IndexDataConnection"}:
        module_name = "dataspear.connections"
    elif name in {"Transport", "BaseConnection"}:
        module_name = "dataspear.base"
    else:
        module_name = _TOOL_MODULES.get(category)

    if not module_name:
        return None
    target: Any = importlib.import_module(module_name)
    for part in name.split("."):
        target = getattr(target, part, None)
        if target is None:
            return None
    return target if callable(target) else None


def _signature_details(tool: Callable[..., Any]) -> tuple[str, str, str]:
    """Return signature, required arguments, and optional arguments for a tool."""
    try:
        signature = inspect.signature(tool)
    except (TypeError, ValueError):
        return "(...)", "unknown", "unknown"

    required: list[str] = []
    optional: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.name in {"self", "cls"}:
            continue
        label = str(parameter)
        if parameter.default is inspect.Parameter.empty:
            required.append(label)
        else:
            optional.append(label)
    return str(signature), ", ".join(required) or "none", ", ".join(optional) or "none"


# NSE option chain
_register("option_chain", "fetch_option_chain",
          "Fetch raw NSE v3 option-chain JSON (optionally per expiry).")
_register("option_chain", "parse_option_chain",
          "Parse raw NSE v3 JSON into an OptionChain model.")
_register("option_chain", "get_nifty_option_chain",
          "Fetch + parse NIFTY chain; optional atm_range filter.")
_register("option_chain", "get_expiry_dates",
          "List available NIFTY expiry dates (contract-info then chain fallback).")

# NSE models / OI
_register("oi", "OptionChain", "Parsed NIFTY option chain dataclass.")
_register("oi", "OptionQuote", "One CE/PE leg of a strike.")
_register("oi", "OptionStrike", "One strike row with CE + PE.")
_register("oi", "pcr_sentiment", "Interpret a Put-Call Ratio into a sentiment string.")
_register("oi", "max_pain",
          "Strike where option writers lose the least at expiry.")
_register("oi", "top_oi_strikes",
          "Top N strikes by CE or PE open interest.")
_register("oi", "support_resistance",
          "OI-based walls: top PE OI = support, top CE OI = resistance.")
_register("oi", "oi_buildup_unwinding",
          "Fresh OI writing and unwinding per side.")
_register("oi", "iv_skew", "CE/PE IV for +/- span strikes around ATM.")
_register("oi", "oi_analysis",
          "Full OI summary: PCR, sentiment, max pain, S/R, buildup, IV skew.")

# NSE VIX
_register("vix", "get_india_vix", "Current India VIX level (0.0 on failure).")
_register("vix", "get_india_vix_history",
          "VIX trend over the last N sessions (current/prev/change/avg/trend/regime).")
_register("vix", "get_spot_and_vix",
          "NIFTY spot and India VIX in one round-trip each.")
_register("vix", "vix_regime",
          "Classify a VIX level into LOW_FEAR/NORMAL/ELEVATED/EXTREME_FEAR.")

# NSE levels
_register("levels", "detect_levels",
          "Detect levels across multiple candle timeframes (swing highs/lows, stop-hunt wicks, zones).")
_register("levels", "swing_highs",
          "Recent swing-high pivots (higher than N candles either side).")
_register("levels", "swing_lows",
          "Recent swing-low pivots (lower than N candles either side).")
_register("levels", "wick_levels",
          "Round-number zones hit by recurring long wicks (stop-hunt candidates).")
_register("levels", "distribution_accumulation_zones",
          "High-volume rejection candles split into distribution/accumulation zones.")
_register("levels", "opening_fake_frequency",
          "Count recent daily candles with a small body relative to total range.")
_register("levels", "time_of_day_traps",
          "Flag repeated stop-hunt wicks in the opening window (default 09:30).")
_register("levels", "LevelAnalysis",
          "Detected structural levels + human-readable summary.")
_register("levels", "merge_with_oi_walls",
          "Combine price levels with OI walls into one support/resistance view.")

# NSE option charts
_register("chart", "get_option_chart",
          "Fetch + parse intraday chart for one option contract.")
_register("chart", "fetch_option_chart",
          "Fetch raw NSE chart payload for one option contract.")
_register("chart", "get_both_charts",
          "Fetch CE and PE charts for the same strike. Returns (ce, pe).")
_register("chart", "build_identifier",
          "Build NSE chart identifier OPTIDXNIFTY{DD-MM-YYYY}{CE|PE}{STRIKE:.2f}.")
_register("chart", "parse_chart_data",
          "Parse raw NSE chart payload (note NSE's grapthData typo).")
_register("chart", "OptionChart", "Intraday time series for a single option contract.")
_register("chart", "ChartPoint", "One timestamped price/volume sample.")

# NSE market extras
_register("extras", "get_fii_dii_data",
          "FII/DII cash market activity with a directional read.")
_register("extras", "get_global_indices",
          "Snapshot of major global indices plus trading cues and a bias label.")
_register("extras", "get_nifty_technicals",
          "EMA9/21, VWAP, day high/low and intraday trend from Yahoo 5m candles.")
_register("extras", "get_premarket_data",
          "Pre-market context: NIFTY gap vs previous close + expected open range.")

# NSE market time
_register("time", "get_market_status",
          "Return a fully populated MarketStatus for now (or a given datetime).")
_register("time", "is_market_open",
          "Convenience wrapper: True when NSE is in NORMAL session.")
_register("time", "is_trading_day",
          "True if day is a weekday that is not an NSE holiday.")
_register("time", "next_trading_day",
          "First tradable day on or after from_date.")
_register("time", "NSE_HOLIDAYS",
          "Dict[date, str] of 2025-2026 NSE holidays.")
_register("time", "MarketStatus",
          "Snapshot of the current NSE session state (phase, open, next open, rules...).")

# NSE regime
_register("regime", "detect_regime",
          "Classify current market regime from PCR, VIX, OI walls, technicals.")
_register("regime", "classify_pcr",
          "Granular PCR -> sentiment band (avoids a wide NEUTRAL dead zone).")
_register("regime", "MarketRegime",
          "Regime result: regime, confidence, direction, range, strategy, signals...")

# NSE scanner
_register("scanner", "build_market_brief",
          "One-call snapshot: chain, OI, VIX, regime, strategy, targeted strikes.")
_register("scanner", "select_target_strikes",
          "Pick 2-3 (strike, option_type) targets from the chain's real strikes.")
_register("scanner", "MarketBrief",
          "Everything needed for a decision, in one compact object.")
_register("scanner", "StrikeBrief",
          "Compact data for one targeted strike with chart context.")

# NSE full context
_register("context", "build_market_context",
          "Everything in one concurrent call: brief, status, technicals, global, FII/DII, premarket, news.")
_register("context", "MarketContext",
          "Every section of the market picture, gathered together.")

# NSE session
_register("session", "NseSession",
          "Thread/task-safe NSE session with automatic cookie renewal.")
_register("session", "nse_get",
          "GET an NSE URL using the shared session.")
_register("session", "nse_get_json", "Shared-session GET + .json().")
_register("session", "force_refresh",
          "Force a cookie refresh (call if you start getting 403s mid-session).")
_register("session", "aclose", "Close the shared NSE session.")

# Groww
_register("groww", "get_groww_option_chain",
          "Fetch + parse Groww option chain for an underlying (alias for fetch_groww_option_chain).")
_register("groww", "fetch_groww_option_chain",
          "Fetch + parse Groww option chain from __NEXT_DATA__.")
_register("groww", "get_groww_expiries",
          "List available Groww expiries (alias for fetch_groww_expiries).")
_register("groww", "fetch_groww_expiries",
          "List available Groww expiries for an underlying.")
_register("groww", "get_groww_option_chart",
          "Fetch intraday chart for one Groww option leg (resolves contract_id, falls back to NSE).")
_register("groww", "fetch_groww_option_chart",
          "Fetch intraday chart for a Groww option contract id (segment FNO).")
_register("groww", "fetch_groww_candles",
          "Fetch delayed intraday chart for an index (CASH) or option (FNO) contract.")
_register("groww", "get_groww_levels",
          "Detect price levels from Groww index candles (intraday + daily).")
_register("groww", "find_groww_contract",
          "Resolve the exact Groww contract_id for one strike/expiry/type.")
_register("groww", "build_groww_symbol",
          "Build Groww's contract id for an option (weekly or monthly).")
_register("groww", "fetch_groww_live_price",
          "Fetch + parse live price snapshot for one Groww contract.")
_register("groww", "GrowwOptionChain", "Parsed Groww option chain for one expiry.")
_register("groww", "GrowwChart", "Delayed intraday chart for an index or option contract.")
_register("groww", "GrowwQuote", "One leg (CE or PE) of a Groww option strike.")
_register("groww", "GrowwLiveQuote",
          "Parsed live price snapshot for one Groww contract.")
_register("groww", "GrowwCandle", "A single Groww OHLCV candle.")
_register("groww", "GrowwStrike", "A single strike row with its call and put legs.")

# News
_register("news", "fetch_all_news",
          "All categories (market/fii/rbi-sebi/geopolitical), deduplicated, HIGH impact first.")
_register("news", "fetch_market_news", "Market headlines from Google News RSS.")
_register("news", "fetch_geopolitical_news",
          "Geopolitical headlines (oil, Fed, China, OPEC, sanctions...).")
_register("news", "fetch_rbi_sebi_news",
          "RBI/SEBI policy headlines (repo rate, monetary policy, circuit breaker...).")
_register("news", "fetch_fii_news",
          "FII/FPI flow headlines (buying, selling, institutional investors India).")
_register("news", "fetch_news",
          "Fetch + score headlines for a raw Google News query.")
_register("news", "news_brief",
          "Compact news summary (fetch + render). Turn on fetch_full_content=True for article bodies.")
_register("news", "fetch_article_content",
          "Download one article URL and extract cleaned body text (strip tags/scripts/nav).")
_register("news", "parse_rss",
          "Parse a Google News RSS document into scored, deduplicated NewsArticles.")
_register("news", "score_article",
          "Return (sentiment, impact) for a headline using keyword heuristics.")
_register("news", "render_news_brief",
          "Render a compact summary block from already-fetched articles.")
_register("news", "NewsArticle",
          "Dataclass: title, source, published, url, category, sentiment, impact, full_content.")

# Utils Yahoo
_register("yahoo", "get_candles",
          "Convenience wrapper: fetch Yahoo chart + return parsed Candle list.")
_register("yahoo", "get_quote",
          "Last-price snapshot for a ticker (price/prev_close/change/change_pct).")
_register("yahoo", "fetch_chart",
          "Fetch raw Yahoo chart payload for a ticker (None on failure).")
_register("yahoo", "parse_chart",
          "Parse raw Yahoo chart payload into (meta, candles).")
_register("yahoo", "quote_from_meta",
          "Build {price, prev_close, change, change_pct} from Yahoo meta.")
_register("yahoo", "Candle",
          "A single Yahoo OHLCV candle with body/range/wick/bullish helpers.")

# Utils URL / HTTP
_register("http", "URL.get_url",
          "Build a Groww chart URL from IndexRequestParameters or a raw suffix string.")
_register("http", "RequestHandler",
          "Reusable async HTTP getter with one shared client for connection pooling.")
_register("http", "IndexRequestParameters",
          "Validated request params: suffix, interval, connection_type, start/end/datarange.")
_register("http", "ConnectionType", "IntEnum: Live=1, History=0.")

# Utils time
_register("time_utils", "now_ist", "Current wall-clock time in IST.")
_register("time_utils", "today_ist", "Current IST calendar date.")
_register("time_utils", "to_ist",
          "Convert an epoch (UTC seconds) timestamp into an IST datetime.")
_register("time_utils", "IST",
          "timezone(timedelta(hours=5, minutes=30)) — India Standard Time.")

# Utils validation
_register("validation", "POSSIBLE_SUFFIX_FOR_INDEX_URL",
          "Allowed suffixes: NIFTY, BANKNIFTY, 1 (SENSEX), INDIAVIX, NIFTYIT.")
_register("validation", "POSSIBLE_TIME_INTERVALS",
          "Allowed intervals: 1, 3, 5, 15, 30, 60, 1440 minutes.")

# Config
_register("config", "config",
          "Module-level Config singleton. Call config.load_env() once at startup (safe when no .env).")
_register("config", "Config",
          "Holds api_key, base_url, api_index_route. load_env(path='.env') is optional.")

# Unified request handling: Core fetches request objects (specs)
_register("core", "Core",
          "Fetches request objects: await core.fetch(spec); also try_fetch, fetch_many, get, url_for.")
_register("core", "Result",
          "Envelope from try_fetch/fetch_many: ok, data, error, error_type, elapsed_ms; .unwrap(), .to_dict().")
_register("core", "Transport",
          "ABC: how to reach a provider (base URL + get()). Concrete: HttpTransport, NseTransport.")
_register("core", "BaseConnection",
          "ABC for the long-lived provider connections (declares provider, aclose()).")
_register("specs", "RequestSpec",
          "ABC: one URL to fetch. Implement provider, relative_url(), optionally parse(response).")
_register("specs", "CompositeSpec",
          "ABC: a result needing several requests. Implement execute(core).")
_register("specs", "IndexSpec",
          "Index candles via the configured Groww index route (wraps IndexRequestParameters).")
_register("specs", "GrowwChartSpec", "Groww delayed chart for an index (CASH) or option id (FNO).")
_register("specs", "GrowwOptionChainSpec", "Groww option chain for an underlying/expiry.")
_register("specs", "GrowwLivePriceSpec", "Groww live price and greeks for one contract id.")
_register("specs", "GrowwOptionChartSpec",
          "Option-leg chart from strike/expiry/type: resolves contract, falls back to NSE.")
_register("specs", "NseOptionChainSpec", "NSE NIFTY option chain (optional expiry, atm_range).")
_register("specs", "NseExpirySpec", "NSE NIFTY expiry dates (contract-info, then chain fallback).")
_register("specs", "NseOptionChartSpec", "NSE intraday chart for one option contract.")
_register("specs", "YahooCandlesSpec", "Yahoo OHLCV candles for a ticker.")
_register("specs", "YahooQuoteSpec", "Yahoo last price / change snapshot for a ticker.")
_register("specs", "NewsSpec", "Google News RSS headlines for a query or category, scored.")
_register("specs", "LevelsSpec",
          "Price levels from any candle specs (LevelsSpec.groww(...), LevelsSpec.yahoo(...)).")
_register("specs", "as_spec",
          "Convert IndexRequestParameters / DataConnection into a spec; specs pass through.")

# Core connections
_register("core", "DataConnection",
          "Base async connection: set params, call fetch() -> (error, response).")
_register("core", "IndexDataConnection",
          "Preconfigured index connection (suffix + interval + range) for Groww chart route.")


def ai_tool_tip() -> tuple[str, dict[str, Callable[..., Any]]]:
    """Return a prompt describing every tool in dataspear plus a name->ref dict.

    Returns
    -------
    prompt : str
        Plain-text tool contract grouped by category, suitable for pasting into
        an LLM context window.  Every entry includes its exact Python signature,
        required/optional parameters, whether it is async, and a call pattern.
    tool_map : dict[str, callable]
        ``{tool_name: callable_object}`` for every callable capability.  Values
        are the actual function, bound method, or class object; non-callable
        constants are documented in ``prompt`` but omitted from this mapping.

    Example
    -------
        prompt, tools = ai_tool_tip()
        print(prompt)                 # hand to an LLM
        chain_fn = tools["get_nifty_option_chain"]
        chain = await chain_fn(atm_range=10)
    """
    lines: list[str] = []
    lines.append("=== DATASPEAR TOOLKIT ===")
    lines.append("")
    lines.append("dataspear is a lightweight async data layer for Indian markets.")
    lines.append("Every network call is a coroutine; compose with asyncio.gather.")
    lines.append("Import from dataspear, dataspear.nse, dataspear.groww, dataspear.news,")
    lines.append("dataspear.utils.yahoo, dataspear.utils.url, dataspear.utils.time,")
    lines.append("dataspear.utils.request_handler, dataspear.utils.validation,")
    lines.append("dataspear.core, dataspear.settings (configurable defaults).")
    lines.append("")
    lines.append("HOW TO CALL THE TOOL MAP")
    lines.append("  - Look up the exact name: tool = tools['get_nifty_option_chain'].")
    lines.append("  - For entries marked async: result = await tool(required_arg=value, ...).")
    lines.append("  - For entries marked sync: result = tool(required_arg=value, ...).")
    lines.append("  - Classes are callable constructors. Instantiate them only when the task needs a model/spec.")
    lines.append("  - Use the signature and required/optional fields below exactly; do not invent arguments.")
    lines.append("")
    lines.append("CONFIG (call once at startup)")
    lines.append("  from dataspear.config import config")
    lines.append("  config.load_env()            # safe when no .env exists")
    lines.append("  # env vars: DATASPEAR_BASE_URL, DATASPEAR_API_INDEX_ROUTE, DATASPEAR_API_KEY")
    lines.append("")
    lines.append("UNIFIED REQUESTS (preferred entry point)")
    lines.append("  Build a request object; Core joins its relative URL to the provider base URL,")
    lines.append("  fetches it with the right transport and returns the parsed model.")
    lines.append("  from dataspear import Core, IndexSpec, GrowwOptionChainSpec, LevelsSpec")
    lines.append("  async with Core.with_defaults() as core:")
    lines.append("      chart = await core.fetch(IndexSpec(suffix='NIFTY', interval=5))")
    lines.append("      chain = await core.fetch(GrowwOptionChainSpec('NIFTY', expiry='2026-10-08'))")
    lines.append("      lvls  = await core.fetch(LevelsSpec.groww('NIFTY'))")
    lines.append("      res   = await core.fetch_many([NseOptionChainSpec(), YahooQuoteSpec('^INDIAVIX')])")
    lines.append("      # fetch raises; try_fetch/fetch_many return Result(ok, data, error) and never raise")
    lines.append("  Providers: index, groww, nse, yahoo, news. Custom source: subclass RequestSpec.")
    lines.append("")
    lines.append("CLEANUP (at process exit)")
    lines.append("  from dataspear.nse import aclose")
    lines.append("  await aclose()")
    lines.append("")

    # Group by category, alphabetical within group.
    resolved_tools: dict[str, Callable[..., Any]] = {}
    by_cat: dict[str, list[tuple[str, str, Callable[..., Any] | None]]] = {}
    for name, (cat, desc, fn) in sorted(_TOOL_REGISTRY.items()):
        tool = fn or _resolve_tool(cat, name)
        if tool is not None:
            resolved_tools[name] = tool
        by_cat.setdefault(cat, []).append((name, desc, tool))

    for cat in sorted(by_cat):
        items = by_cat[cat]
        lines.append(f"--- {cat.upper()} ---")
        for name, desc, tool in items:
            if tool is None:
                lines.append(f"  {name}: {desc} (reference value; not callable)")
                continue
            signature, required, optional = _signature_details(tool)
            async_label = "async" if inspect.iscoroutinefunction(tool) else "sync"
            kind = "class" if inspect.isclass(tool) else "function"
            lines.append(f"  {name}{signature} [{async_label} {kind}]")
            lines.append(f"    Purpose: {desc}")
            lines.append(f"    Required: {required}")
            lines.append(f"    Optional: {optional}")
            call = f"await tools['{name}'](...)" if async_label == "async" else f"tools['{name}'](...)"
            lines.append(f"    Call: {call}")
        lines.append("")

    lines.append("=== END DATASPEAR TOOLKIT ===")
    prompt = "\n".join(lines)

    return prompt, resolved_tools
