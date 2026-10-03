"""Extra market context beyond the option chain.

* :func:`get_fii_dii_data`      - FII/DII cash + derivatives activity (NSE)
* :func:`get_global_indices`    - S&P/Nasdaq/Nikkei/Hang Seng/Crude/DXY snapshot
* :func:`get_nifty_technicals`  - EMA9/21, VWAP, day high/low, intraday trend
* :func:`get_premarket_data`    - NIFTY gap vs previous close + expected open

NSE calls reuse the shared async session; the rest go through Yahoo.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from dataspear.settings import NSE_BASE_URL
from dataspear.nse.session import nse_get
from dataspear.utils.time import now_ist, to_ist
from dataspear.utils.yahoo import Candle, get_candles, get_quote

log = logging.getLogger(__name__)

NIFTY_TICKER = "^NSEI"

FII_DII_URL = f"{NSE_BASE_URL}/api/fiidiiTradeReact"

GLOBAL_TICKERS: Dict[str, str] = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "hangseng": "^HSI",
    "nikkei": "^N225",
    "ftse": "^FTSE",
    "dax": "^GDAXI",
    "us10y_yield": "^TNX",
    "dollar_index": "DX-Y.NYB",
    "crude_oil": "CL=F",
    "gold": "GC=F",
}


# ── FII / DII activity ─────────────────────────────────────────────────────────


def _fii_signal(net: float) -> str:
    if net > 500:
        return "STRONG_BUYING"
    if net > 0:
        return "BUYING"
    if net > -500:
        return "SELLING"
    return "HEAVY_SELLING"


async def get_fii_dii_data() -> dict:
    """FII + DII cash market activity with a directional read."""
    try:
        resp = await nse_get(FII_DII_URL)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        log.warning("FII/DII fetch failed: %s", exc)
        return {"error": str(exc), "source": "NSE India (failed)"}

    result: dict = {"source": "NSE India"}

    for entry in data or []:
        category = str(entry.get("category", "")).upper()
        buy = float(entry.get("buyValue", 0) or 0)
        sell = float(entry.get("sellValue", 0) or 0)
        net = float(entry.get("netValue", 0) or 0)
        if "FII" in category or "FPI" in category:
            result.update(
                fii_cash_buy=buy, fii_cash_sell=sell, fii_cash_net=net
            )
        elif "DII" in category:
            result.update(
                dii_cash_buy=buy, dii_cash_sell=sell, dii_cash_net=net
            )

    fii_net = result.get("fii_cash_net", 0.0)
    dii_net = result.get("dii_cash_net", 0.0)
    result["fii_signal"] = _fii_signal(fii_net)
    result["dii_signal"] = "BUYING" if dii_net > 0 else "SELLING"
    combined = fii_net + dii_net
    result["combined_net"] = round(combined, 2)
    result["market_signal"] = "BULLISH" if combined > 0 else "BEARISH"
    return result


# ── Global indices ─────────────────────────────────────────────────────────────


def _global_cues(result: dict) -> List[str]:
    cues: List[str] = []
    for key in ("sp500", "nasdaq"):
        chng = result.get(key, {}).get("change_pct", 0)
        if abs(chng) > 0.5:
            direction = "up" if chng > 0 else "down"
            cues.append(
                f"US markets {direction} {abs(chng):.1f}% -> NIFTY gap "
                f"{direction} likely"
            )
    crude = result.get("crude_oil", {}).get("change_pct", 0)
    if abs(crude) > 1.5:
        direction = "higher" if crude > 0 else "lower"
        cues.append(
            f"Crude oil {direction} {abs(crude):.1f}% -> "
            "inflation/current-account pressure"
        )
    dxy = result.get("dollar_index", {}).get("change_pct", 0)
    if abs(dxy) > 0.3:
        direction = "stronger" if dxy > 0 else "weaker"
        flow = "out of" if dxy > 0 else "into"
        cues.append(f"Dollar {direction} -> FII flows {flow} India likely")
    return cues


def _global_bias(result: dict) -> str:
    keys = ("sp500", "nasdaq", "nikkei", "hangseng")
    up = sum(1 for k in keys if result.get(k, {}).get("change_pct", 0) > 0)
    down = sum(1 for k in keys if result.get(k, {}).get("change_pct", 0) < 0)
    if up >= 3:
        return "BULLISH"
    if down >= 3:
        return "BEARISH"
    return "MIXED"


async def get_global_indices() -> dict:
    """Snapshot of major global indices plus trading cues and a bias label."""
    keys = list(GLOBAL_TICKERS)
    quotes = await asyncio.gather(
        *(get_quote(GLOBAL_TICKERS[k]) for k in keys), return_exceptions=True
    )

    result: dict = {}
    for key, quote_ in zip(keys, quotes):
        if isinstance(quote_, Exception) or not quote_:
            result[key] = {"price": 0.0, "change_pct": 0.0}
            continue
        result[key] = {
            "price": quote_.get("price", 0.0),
            "change_pct": quote_.get("change_pct", 0.0),
        }

    result["trading_cues"] = _global_cues(result)
    result["global_bias"] = _global_bias(result)
    return result


# ── NIFTY intraday technicals ──────────────────────────────────────────────────


def _ema(values: List[float], span: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (span + 1)
    ema = values[0]
    for value in values[1:]:
        ema = value * k + ema * (1 - k)
    return ema


def _technical_trend(
    ltp: float, ema9: float, ema21: float, vwap: float
) -> str:
    if ltp > ema9 > ema21 and ltp > vwap:
        return "STRONG_UPTREND"
    if ltp > ema9 and ltp > vwap:
        return "UPTREND"
    if ltp < ema9 < ema21 and ltp < vwap:
        return "STRONG_DOWNTREND"
    if ltp < ema9 and ltp < vwap:
        return "DOWNTREND"
    return "SIDEWAYS"


def _bias_from_trend(trend: str) -> str:
    if "UPTREND" in trend:
        return "BULLISH"
    if "DOWNTREND" in trend:
        return "BEARISH"
    return "NEUTRAL"


def _compute_technicals(candles: List[Candle]) -> dict:
    """Pure technicals computation from today's 5-minute candles."""
    today = now_ist().date()
    today_candles = [
        c for c in candles if to_ist(c.timestamp).date() == today
    ]
    if not today_candles:
        today_candles = candles

    if len(today_candles) < 2:
        return {}

    closes = [c.close for c in today_candles]
    ltp = round(closes[-1], 2)
    ema9 = round(_ema(closes, 9), 2)
    ema21 = round(_ema(closes, 21), 2)
    day_high = round(max(c.high for c in today_candles), 2)
    day_low = round(min(c.low for c in today_candles), 2)

    total_vol = sum(c.volume for c in today_candles)
    if total_vol > 0:
        typical_vol = sum(
            ((c.high + c.low + c.close) / 3) * c.volume for c in today_candles
        )
        vwap = round(typical_vol / total_vol, 2)
    else:
        vwap = ltp

    trend = _technical_trend(ltp, ema9, ema21, vwap)
    return {
        "ltp": ltp,
        "ema9": ema9,
        "ema21": ema21,
        "vwap": vwap,
        "day_high": day_high,
        "day_low": day_low,
        "trend": trend,
        "tech_bias": _bias_from_trend(trend),
        "candles": len(today_candles),
    }


async def get_nifty_technicals() -> dict:
    """EMA9/21, VWAP, day high/low and intraday trend from Yahoo 5m candles."""
    candles = await get_candles(NIFTY_TICKER, range_="2d", interval="5m")
    return _compute_technicals(candles)


# ── Pre-market gap ─────────────────────────────────────────────────────────────


def _premarket_from_quote(quote_: dict) -> dict:
    spot = float(quote_.get("price", 0.0))
    prev_close = float(quote_.get("prev_close", 0.0))
    if spot <= 0 or prev_close <= 0:
        return {"error": "Unavailable pre-market data"}

    gap = round(spot - prev_close, 2)
    gap_pct = round(gap / prev_close * 100, 2)
    if gap > 0:
        gap_dir = "GAP_UP"
    elif gap < 0:
        gap_dir = "GAP_DOWN"
    else:
        gap_dir = "FLAT"

    return {
        "prev_close": prev_close,
        "gift_nifty": spot,
        "gap_points": gap,
        "gap_pct": gap_pct,
        "gap_direction": gap_dir,
        "expected_open_range": (
            f"{round(spot * 0.997):.0f}-{round(spot * 1.003):.0f}"
        ),
        "trade_note": (
            f"Expected {gap_dir} of {abs(gap_pct):.2f}% ({abs(gap):.0f} pts). "
            + (
                "Watch for gap fill OR continuation past first 5-min candle."
                if abs(gap_pct) > 0.3
                else "Flat open - wait for 09:30 before taking direction."
            )
        ),
    }


async def get_premarket_data() -> dict:
    """Pre-market context: NIFTY gap vs previous close + expected open range."""
    quote_ = await get_quote(NIFTY_TICKER)
    return _premarket_from_quote(quote_)
