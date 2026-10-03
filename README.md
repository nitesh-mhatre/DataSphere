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
├── core.py                     AI tool catalog and ai_tool_tip()
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
| `dataspear.core` | `ai_tool_tip()`. | Builds a grouped text catalog of package tools and a name-to-callable mapping. Also re-exports legacy `DataConnection` and `IndexDataConnection`. |
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
