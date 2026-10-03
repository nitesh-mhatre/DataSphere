# DataSpear

A lightweight, dependency-light data fetching library for Indian financial
market data, designed so multiple projects can share one data layer.

Runtime dependencies are just `httpx` and `python-dotenv`; market data is
fetched directly from NSE India and Yahoo Finance over async HTTP.

## Install

```bash
pip install -e .
```

## Modules

| Module | Provides |
|---|---|
| `dataspear.nse.session` | Async NSE session with cookie warmup + 403 retry |
| `dataspear.nse.option_chain` | NIFTY option chain fetch/parse, **expiry search**, ATM filter |
| `dataspear.nse.analysis` | **Open interest** analysis: PCR, sentiment, max pain, CE/PE walls, buildup/unwinding, IV skew |
| `dataspear.nse.vix` | **India VIX** spot, 5-day history, trend, regime |
| `dataspear.nse.levels` | **Level detection**: swing highs/lows, wick (stop-hunt) levels, distribution/accumulation zones |
| `dataspear.nse.option_chart` | Per-strike intraday price/volume time series |
| `dataspear.nse.market_extra` | FII/DII activity, global indices, NIFTY technicals (EMA/VWAP), pre-market gap |
| `dataspear.nse.market_time` | NSE session phase, holidays, next trading day, time-based rules |
| `dataspear.nse.regime` | Market regime classifier (SIDEWAYS / DIRECTIONAL / VOLATILE) |
| `dataspear.nse.scanner` | `MarketBrief`: one aggregated snapshot (chain + VIX + regime + session) + targeted strikes |
| `dataspear.nse.context` | `MarketContext`: **everything in one call** - brief + macro + news, fetched concurrently |
| `dataspear.news` | Google News RSS feed with sentiment/impact scoring |
| `dataspear.utils.yahoo` | Async Yahoo chart client: OHLCV candles + quotes |
| `dataspear.utils.time` | Shared IST timezone helpers (`IST`, `now_ist`, `to_ist`) |

Everything network-bound is `async`, so calls can be composed with
`asyncio.gather`.

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
