# DataSpear

A lightweight, dependency-light data fetching library for Indian financial
market data, designed so multiple projects can share one data layer.

Runtime dependencies are just `httpx` and `python-dotenv`; market data is
fetched directly from NSE India and Yahoo Finance over async HTTP.

## Install

```bash
pip install -e .
```

## Source tree

```text
src/dataspear/
├── __init__.py                 Public package exports
├── settings.py                 Shared endpoints, headers, timeouts, and Config/Settings
├── config.py                   Backward-compatible settings import path
├── connections.py              Provider connection classes
├── core.py                     Core request handler, transports, Result, ai_tool_tip()
├── base.py                     ABCs: Transport, RequestSpec, CompositeSpec, BaseConnection
├── transports.py               HttpTransport, NseTransport
├── specs.py                    Request objects (relative URL + parser) that Core fetches
├── errors.py                   DataSpearError, UnknownProviderError, InvalidParametersError
├── groww.py                    Groww models, parsers, and data operations
├── news.py                     News models, RSS parsing, scoring, and retrieval
├── nse/
│   ├── __init__.py              NSE public exports
│   ├── session.py               Cookie-managed NSE HTTP session
│   ├── models.py                Option chain data models
│   ├── option_chain.py          Option-chain retrieval and parsing
│   ├── analysis.py              Open-interest analytics
│   ├── option_chart.py          Per-contract chart retrieval and parsing
│   ├── levels.py                Price-level analysis
│   ├── vix.py                   India VIX helpers
│   ├── market_time.py           NSE calendar and market hours
│   ├── market_extra.py          Macro, technical, and pre-market data
│   ├── regime.py                Market regime classification
│   ├── scanner.py               Aggregated MarketBrief
│   └── context.py               Aggregated MarketContext
└── utils/
    ├── http.py                  Shared one-shot async HTTP helpers
    ├── request_handler.py       Pooled Groww index-route HTTP client
    ├── url.py                   Groww index-route URL builder
    ├── validation.py            Index request parameters and enums
    ├── time.py                  IST date/time helpers
    └── yahoo.py                 Yahoo chart/quote client and Candle model
```

Everything network-bound is `async`, so calls can be composed with
`asyncio.gather`. Parsing, calculations, and model conversion functions are
synchronous unless noted below.

## Module API reference

### Package entry points and shared infrastructure

| Module | Public classes, methods, and functions | Purpose |
|---|---|---|
| `dataspear` | Re-exports common settings, connections, Groww/news models and functions, and selected NSE APIs. | Convenient top-level imports; the canonical implementations live in their feature modules. |
| `dataspear.settings` | `Config` / `Settings`; `Config.load_env(path=".env")`; singleton `config`; provider endpoint, header, timeout, and retry constants. | Shared package defaults and environment-backed Groww index-route configuration. `Settings` is an alias of `Config`. |
| `dataspear.config` | `Config`, `Settings`, `config`, `DEFAULT_BASE_URL`, `DEFAULT_API_INDEX_ROUTE`. | Compatibility import path; new code can use `dataspear.settings`. |
| `dataspear.connections` | `DataConnection.fetch()`, `DataConnection.aclose()`; `IndexDataConnection`; `GrowwDataConnection.fetch_candles()`, `.fetch_option_chain()`, `.fetch_expiries()`, `.fetch_live_price()`; `NseDataConnection.fetch()`, `.fetch_json()`; `NewsConnection.fetch()`. | Configured source facades. The legacy `DataConnection`/`IndexDataConnection` target the Groww index chart endpoint and return `(error, response)`. Provider-specific facades return parsed data. |
| `dataspear.core` | `Core` (`with_defaults()`, `register_transport()`, `fetch()`, `try_fetch()`, `fetch_many()`, `get()`, `url_for()`, `aclose()`); `Transport`, `HttpTransport`, `NseTransport`; `Result` (`unwrap()`, `to_dict()`); `ai_tool_tip()`. | The single place that performs HTTP. Receives request objects, joins their relative URL to the provider's base URL, fetches, and returns the parsed result. Also re-exports legacy `DataConnection` and `IndexDataConnection`. |
| `dataspear.base` | `Transport`, `RequestSpec`, `CompositeSpec`, `BaseConnection` (all `abc.ABC`). | The contracts. Read this module first. |
| `dataspear.transports` | `HttpTransport`, `NseTransport`. | Concrete transports. |
| `dataspear.specs` | `RequestSpec`, `CompositeSpec`, `IndexSpec`, `GrowwChartSpec`, `GrowwOptionChainSpec`, `GrowwLivePriceSpec`, `GrowwOptionChartSpec`, `NseOptionChainSpec`, `NseExpirySpec`, `NseOptionChartSpec`, `YahooCandlesSpec`, `YahooQuoteSpec`, `NewsSpec`, `LevelsSpec`, `as_spec()`. | Request objects. Each knows its `provider`, builds its own `relative_url()` and parses the response into the module's model. Composite specs (option chart, levels) fetch several parts through the same core. |
| `dataspear.utils.http` | `get_response()`, `get_json()`, `get_text()`. | Shared one-shot async GET helpers. Feature modules handle provider-specific errors and fallbacks. |
| `dataspear.utils.request_handler` | `RequestHandler.fetch()`, `.aclose()`. | Reusable pooled HTTP client for the configured Groww index route; returns `(error, response)`. |
| `dataspear.utils.url` | `URL.get_url()`. | Builds an index-route URL from `IndexRequestParameters` or a raw path suffix. Reads the active config at call time. |
| `dataspear.utils.validation` | `ConnectionType`; `IndexRequestParameters.validate()`. | Defines Live/History request mode and validates symbols, intervals, and time windows. |
| `dataspear.utils.time` | `IST`, `now_ist()`, `today_ist()`, `to_ist()`. | Common India Standard Time timezone and timestamp conversion helpers. |

### Groww and news

| Module | Public classes, methods, and functions | Purpose |
|---|---|---|
| `dataspear.groww` | Models: `GrowwCandle` (`to_dict()`, `as_candle()`), `GrowwChart` (`last_price`, `high`, `low`, `total_volume`, `as_candles()`, `to_dict()`), `GrowwQuote`, `GrowwLiveQuote`, `GrowwStrike`, `GrowwOptionChain` (`atm_strike`, `to_dict()`). Parsers: `parse_candles()`, `parse_chart()`, `parse_next_data()`, `parse_option_chain()`. Operations: `build_groww_symbol()`, `fetch_groww_candles()`, `fetch_groww_option_chart()`, `fetch_groww_expiries()`, `fetch_groww_option_chain()`, `fetch_groww_live_price()`, `find_groww_contract()`, `get_groww_option_chart()`, `get_groww_levels()`, `get_groww_expiries()`, `get_groww_option_chain()`. | Groww option-chain, quote, and candle data. Option charts can fall back to NSE when Groww has no FNO candles; levels reuse the NSE level analyzer. |
| `dataspear.news` | `NewsArticle` (`one_line()`, `to_dict()`); `score_article()`, `parse_rss()`, `fetch_article_content()`, `fetch_news()`, `fetch_market_news()`, `fetch_geopolitical_news()`, `fetch_rbi_sebi_news()`, `fetch_fii_news()`, `fetch_all_news()`, `render_news_brief()`, `news_brief()`. | Fetches Google News RSS, scores sentiment/impact, optionally downloads article text, and renders summaries. |

### NSE features

| Module | Public classes, methods, and functions | Purpose |
|---|---|---|
| `dataspear.nse` | Re-exports the commonly used NSE models, fetchers, analysis functions, session controls, and aggregators. | Short import path for the NSE API. |
| `dataspear.nse.session` | `NseSession.get()`, `.get_json()`, `.aclose()`, `.force_refresh()`; module functions `nse_get()`, `nse_get_json()`, `force_refresh()`, `aclose()`. | Maintains NSE cookies, warms the session, and retries requests after authorization failures. |
| `dataspear.nse.models` | `OptionQuote` (`oi_change_pct`, `to_dict()`); `OptionStrike` (`to_dict()`); `OptionChain` (`ce_oi_total`, `pe_oi_total`, `pcr`, `strike_prices`, `atm_strike`, `filter_atm()`, `to_dict()`). | Typed option-chain and strike data with common derived values. |
| `dataspear.nse.option_chain` | `fetch_option_chain()`, `parse_option_chain()`, `get_expiry_dates()`, `get_nifty_option_chain()`. | Fetches/parses the NIFTY chain, discovers expiries, and optionally filters around ATM. |
| `dataspear.nse.analysis` | `pcr_sentiment()`, `max_pain()`, `top_oi_strikes()`, `support_resistance()`, `oi_buildup_unwinding()`, `iv_skew()`, `oi_analysis()`. | Pure calculations over an `OptionChain`: PCR, max pain, OI walls, buildup/unwinding, IV skew, and combined summary. |
| `dataspear.nse.option_chart` | `ChartPoint.to_dict()`; `OptionChart` (`last_price`, `high`, `low`, `total_volume`, `trend()`, `to_dict()`); `build_identifier()`, `parse_chart_data()`, `fetch_option_chart()`, `get_option_chart()`, `get_both_charts()`. | Builds NSE option identifiers and retrieves/parses intraday price and volume points. |
| `dataspear.nse.levels` | `LevelAnalysis.to_dict()`; `swing_highs()`, `swing_lows()`, `wick_levels()`, `distribution_accumulation_zones()`, `opening_fake_frequency()`, `time_of_day_traps()`, `detect_levels()`, `merge_with_oi_walls()`. | Detects multi-timeframe price structure and combines it with option-chain support/resistance. |
| `dataspear.nse.vix` | `vix_regime()`, `get_india_vix()`, `get_india_vix_history()`, `get_spot_and_vix()`. | Reads current/history India VIX and classifies volatility conditions. |
| `dataspear.nse.market_time` | `MarketStatus` (`weekday_name`, `context_block()`, `to_dict()`); `is_trading_day()`, `next_trading_day()`, `get_market_status()`, `is_market_open()`, `NSE_HOLIDAYS`. | Reports NSE session phase, trading-day status, holidays, and next open. |
| `dataspear.nse.market_extra` | `get_fii_dii_data()`, `get_global_indices()`, `get_nifty_technicals()`, `get_premarket_data()`. | Retrieves institutional flows and global market cues, and calculates NIFTY technical/pre-market context. |
| `dataspear.nse.regime` | `MarketRegime` (`is_sideways`, `is_directional`, `is_volatile`, `prompt_block()`, `to_dict()`); `classify_pcr()`, `detect_regime()`. | Classifies conditions and produces directional/range/strategy context. |
| `dataspear.nse.scanner` | `StrikeBrief.to_dict()`; `MarketBrief.to_dict()`; `select_target_strikes()`, `build_market_brief()`. | Combines chain, OI, VIX, regime, market hours, and selected option charts into a compact snapshot. |
| `dataspear.nse.context` | `MarketContext.to_dict()`; `build_market_context()`. | Gathers the scanner brief, status, technicals, global cues, FII/DII, pre-market data, and news concurrently. |

### Yahoo Finance

| Module | Public classes, methods, and functions | Purpose |
|---|---|---|
| `dataspear.utils.yahoo` | `Candle` (`body`, `total_range`, `is_bullish`, `wick_up`, `wick_down`, `to_dict()`); `parse_chart()`, `fetch_chart()`, `get_candles()`, `quote_from_meta()`, `get_quote()`. | Retrieves Yahoo chart data and exposes common candle and quote representations used by the NSE analytics. |

This reference covers public APIs. Names prefixed with `_` are internal
implementation helpers and are omitted.

Everything network-bound is `async`, so calls can be composed with
`asyncio.gather`.

## Core and request objects

`Core` is the one place that talks to the network. You give it a **request
object**; the object builds its *relative* URL, the core joins it to the
provider's base URL, fetches it with the right transport, and the object parses
the response:

```text
IndexSpec / GrowwOptionChainSpec / NseOptionChartSpec / LevelsSpec ...
        |  provider = "groww"          relative_url() = "/options/nifty?expiry=..."
        v
Core --> transport["groww"]  (base https://groww.in, Groww headers, pooled client)
     --> GET https://groww.in/options/nifty?expiry=...
        |
        v  spec.parse(response)  ->  GrowwOptionChain
```

```python
from dataspear import (Core, IndexSpec, GrowwOptionChainSpec, GrowwOptionChartSpec,
                       NseOptionChainSpec, YahooQuoteSpec, LevelsSpec)

async with Core.with_defaults() as core:
    chart = await core.fetch(IndexSpec(suffix="NIFTY", interval=5, data_range=60))
    chain = await core.fetch(GrowwOptionChainSpec("NIFTY", expiry="2026-10-08"))
    leg   = await core.fetch(GrowwOptionChartSpec("2026-10-08", 25000, "CE"))
    lvls  = await core.fetch(LevelsSpec.groww("NIFTY"))   # intraday + daily, one call

    core.url_for(IndexSpec("NIFTY"))        # inspect the absolute URL without fetching

    results = await core.fetch_many([       # concurrent, any provider mix, order kept
        NseOptionChainSpec(atm_range=10),
        YahooQuoteSpec("^INDIAVIX"),
        LevelsSpec.yahoo("^NSEI"),
    ])
    for r in results:
        print(r.spec, r.ok, r.error)        # fetch_many/try_fetch never raise
```

`fetch()` raises on failure; `try_fetch()` / `fetch_many()` return
`Result(ok, data, error, error_type, elapsed_ms)` (`.to_dict()` is JSON-friendly,
`.unwrap()` re-raises). Default timeout is 30 s (`Core(timeout=...)`).

The original index objects work unchanged: pass an `IndexRequestParameters`,
`DataConnection` or `IndexDataConnection` straight to `core.fetch(...)`. The
index route's base URL and path are read from `config` at request time, so
`config.load_env()` still applies.

| Provider (transport) | Request objects |
|---|---|
| `index` (config base URL) | `IndexSpec` |
| `groww` | `GrowwChartSpec`, `GrowwOptionChainSpec`, `GrowwLivePriceSpec`, `GrowwOptionChartSpec`\* |
| `nse` (cookie session) | `NseOptionChainSpec`, `NseExpirySpec`\*, `NseOptionChartSpec` |
| `yahoo` | `YahooCandlesSpec`, `YahooQuoteSpec` |
| `news` | `NewsSpec` |
| composite | `LevelsSpec` (any candle sources: `.groww()`, `.yahoo()`, or your own) |

\* composite: resolves or falls back across several requests, all through the core.

### Class design (all `abc.ABC`)

Every extension point is an abstract base class in `dataspear/base.py`. A
subclass that forgets a required member cannot be created, so mistakes show up
immediately with a clear `TypeError`.

```text
Transport (ABC)          HOW to reach a provider           must implement: get()
 |- HttpTransport        plain pooled HTTP
 `- NseTransport         NSE cookie session

RequestSpec (ABC)        WHAT to fetch from one URL        must implement: provider, relative_url()
 |                                                         may override:    parse()
 |- IndexSpec, GrowwChartSpec, GrowwOptionChainSpec, GrowwLivePriceSpec,
 |  NseOptionChainSpec, NseOptionChartSpec, NewsSpec
 |- _YahooSpec (ABC) -> YahooCandlesSpec, YahooQuoteSpec     (must implement parse())
 `- CompositeSpec (ABC)  WHAT to fetch in several steps    must implement: execute(core)
     |- GrowwOptionChartSpec, NseExpirySpec, LevelsSpec

BaseConnection (ABC)     long-lived provider facade        must implement: provider
 `- DataConnection (-> IndexDataConnection), GrowwDataConnection,
    NseDataConnection, NewsConnection
```

| To add... | Subclass | Implement |
|---|---|---|
| a new data endpoint | `RequestSpec` | `provider`, `relative_url()`, usually `parse()` |
| something needing 2+ requests | `CompositeSpec` | `execute(core)` calling `await core.fetch(...)` |
| a new host / auth scheme | `Transport` | `get()` |

`provider` is the name that links a request object to its transport
(`"groww"`, `"nse"`, `"yahoo"`, `"news"`, `"index"`).

**Adding a source** needs no change to the core: write a spec and, if it is a
new host, register a transport.

```python
from dataspear import HttpTransport, RequestSpec

class FxSpec(RequestSpec):
    provider = "fx"
    def __init__(self, pair="USDINR"): self.pair = pair
    def relative_url(self): return f"/rates/{self.pair}"
    def parse(self, response): return response.json()["rate"]

core.register_transport("fx", HttpTransport("https://fx.example.com"))
rate = await core.fetch(FxSpec("USDINR"))
```

Not yet routed through the core: the aggregators (`build_market_brief`,
`build_market_context`, FII/DII, global indices, pre-market, technicals) still
make their own requests internally.

## Connections

Use feature functions for one-off requests. For a configured data source in a
long-running application, use the matching connection type:

```python
from dataspear import GrowwDataConnection, NewsConnection, NseDataConnection

groww = GrowwDataConnection("NIFTY")
candles = await groww.fetch_candles(interval=5, data_range=60)
expiries = await groww.fetch_expiries()

news = NewsConnection(category="fii_flow")
articles = await news.fetch(days=1)

nse = NseDataConnection("https://www.nseindia.com/api/allIndices")
payload = await nse.fetch_json()
```

`DataConnection` and `IndexDataConnection` remain available for compatibility
with the original Groww index-chart API. Their `fetch()` result is the legacy
`(error, response)` tuple; provider-specific connections return parsed data.

## Examples

```python
import asyncio
from dataspear.nse import (
    get_nifty_option_chain,
    get_expiry_dates,
    oi_analysis,
    get_india_vix_history,
    build_market_brief,
    build_market_context,
    get_market_status,
)


async def main():
    expiries = await get_expiry_dates()          # expiry search
    chain = await get_nifty_option_chain(expiry=expiries[0], atm_range=10)
    print(oi_analysis(chain)["max_pain"])        # open interest

    print((await get_india_vix_history())["regime"])   # VIX

    status = get_market_status()
    if status.is_open:
        brief = await build_market_brief()       # aggregate snapshot
        print(brief.spot, brief.pcr, brief.vix, brief.sentiment)
        print(brief.regime, brief.strategy, brief.market_phase)

        ctx = await build_market_context()       # everything at once
        print(ctx.brief.regime, ctx.global_indices["global_bias"], len(ctx.news))


asyncio.run(main())
```

Level detection works on plain candles (e.g. from Yahoo or any source):

```python
from dataspear.utils.yahoo import get_candles
from dataspear.nse.levels import detect_levels

candles = await get_candles("^NSEI", range_="1mo", interval="30m")
levels = detect_levels([candles])
print(levels.stop_hunt_levels, levels.swing_highs)
```

## Config

Copy `.env.example` to `.env` and set `DATASPEAR_BASE_URL`,
`DATASPEAR_API_INDEX_ROUTE` and `DATASPEAR_API_KEY` for the Groww index
route, then call `config.load_env(".env")`.

## Tests

```bash
pytest
```
