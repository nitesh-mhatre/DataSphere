"""AI tool discovery catalog and legacy connection exports.

Provider connection implementations live in :mod:`dataspear.connections`.
"""

from __future__ import annotations

from typing import Any, Callable

# NOTE: dict, list are builtins in Python 3.9+; do not import from typing.

from dataspear.connections import DataConnection, IndexDataConnection

# Public tool registry: every named capability in dataspear, by section.
# Each entry is ``name: (category, description, callable_or_None)``.
# ``callable_or_None`` is a real function reference when the tool is a simple
# importable callable; ``None`` when it is a class, a method, or needs args.

_TOOL_REGISTRY: dict[str, tuple[str, str, Callable[..., Any] | None]] = {}


def _register(
    category: str, name: str, description: str, fn: Callable[..., Any] | None = None
) -> None:
    _TOOL_REGISTRY[name] = (category, description, fn)


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

# Core connections
_register("core", "DataConnection",
          "Base async connection: set params, call fetch() -> (error, response).")
_register("core", "IndexDataConnection",
          "Preconfigured index connection (suffix + interval + range) for Groww chart route.")


def ai_tool_tip() -> tuple[str, dict[str, Callable[..., Any] | None]]:
    """Return a prompt describing every tool in dataspear plus a name->ref dict.

    Returns
    -------
    prompt : str
        Plain-text block listing every tool grouped by category, suitable for
        pasting into an LLM context window so it can call dataspear functions.
    tool_map : dict[str, callable | None]
        ``{tool_name: function_reference}`` for every registered tool.  Items
        that are classes or need arguments map to ``None``; simple stateless
        functions map to the real callable so an agent can *call* them directly.

    Example
    -------
        prompt, tools = ai_tool_tip()
        print(prompt)                 # hand to an LLM
        chain_fn = tools["get_nifty_option_chain"]  # await chain_fn() in async context
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
    lines.append("CALLING CONVENTION")
    lines.append("  - Naked functions (get_nifty_option_chain, news_brief, ...):")
    lines.append("      result = await FUNCTION_NAME(*args, **kwargs)")
    lines.append("  - Classes (OptionChain, MarketContext, ...): instantiate with kwargs.")
    lines.append("  - Everything has .to_dict() for serialization.")
    lines.append("")
    lines.append("CONFIG (call once at startup)")
    lines.append("  from dataspear.config import config")
    lines.append("  config.load_env()            # safe when no .env exists")
    lines.append("  # env vars: DATASPEAR_BASE_URL, DATASPEAR_API_INDEX_ROUTE, DATASPEAR_API_KEY")
    lines.append("")
    lines.append("CLEANUP (at process exit)")
    lines.append("  from dataspear.nse import aclose")
    lines.append("  await aclose()")
    lines.append("")

    # Group by category, alphabetical within group.
    by_cat: dict[str, list[tuple[str, str, Callable[..., Any] | None]]] = {}
    for name, (cat, desc, fn) in sorted(_TOOL_REGISTRY.items()):
        by_cat.setdefault(cat, []).append((name, desc, fn))

    for cat in sorted(by_cat):
        items = by_cat[cat]
        lines.append(f"--- {cat.upper()} ---")
        for name, desc, _ in items:
            lines.append(f"  {name:34s} {desc}")
        lines.append("")

    lines.append("=== END DATASPEAR TOOLKIT ===")
    prompt = "\n".join(lines)

    tool_map: dict[str, Callable[..., Any] | None] = {}
    for name, entry in _TOOL_REGISTRY.items():
        tool_map[name] = entry[2] if len(entry) > 2 else None

    return prompt, tool_map
