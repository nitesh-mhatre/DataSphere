"""NSE NIFTY option chain: fetch, parse, expiry search, ATM filter."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from dataspear.settings import NSE_BASE_URL
from dataspear.nse.models import OptionChain, OptionQuote, OptionStrike
from dataspear.nse.session import nse_get

log = logging.getLogger(__name__)

NSE_BASE = NSE_BASE_URL
OPTION_CHAIN_URL = (
    f"{NSE_BASE}/api/option-chain-v3?type=Indices&symbol=NIFTY"
)
CONTRACT_INFO_URL = f"{NSE_BASE}/api/option-chain-contract-info?symbol=NIFTY"


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_quote(side: Optional[dict]) -> OptionQuote:
    side = side or {}
    return OptionQuote(
        oi=_to_int(side.get("openInterest")),
        change_oi=_to_int(side.get("changeinOpenInterest")),
        volume=_to_int(side.get("totalTradedVolume")),
        iv=_to_float(side.get("impliedVolatility")),
        ltp=_to_float(side.get("lastPrice")),
        change=_to_float(side.get("change")),
        bid=_to_float(side.get("buyPrice1")),
        ask=_to_float(side.get("sellPrice1")),
    )


def parse_option_chain(data: dict, symbol: str = "NIFTY") -> OptionChain:
    """Parse the raw NSE v3 option-chain JSON into an :class:`OptionChain`."""
    records = data.get("records", {}) if isinstance(data, dict) else {}
    spot = _to_float(records.get("underlyingValue"))
    rows = records.get("data", []) or []

    strikes: List[OptionStrike] = []
    expiry = ""
    for item in rows:
        ce = item.get("CE") or {}
        pe = item.get("PE") or {}
        # NSE puts expiryDate inside CE/PE; some payloads also carry it on the row.
        row_expiry = (
            item.get("expiryDate")
            or ce.get("expiryDate")
            or pe.get("expiryDate")
            or ""
        )
        if not expiry and row_expiry:
            expiry = row_expiry
        strikes.append(
            OptionStrike(
                strike=_to_float(item.get("strikePrice")),
                expiry=row_expiry,
                ce=_parse_quote(ce),
                pe=_parse_quote(pe),
            )
        )

    strikes.sort(key=lambda s: s.strike)
    return OptionChain(
        symbol=symbol,
        spot=spot,
        expiry=expiry,
        strikes=strikes,
    )


async def fetch_option_chain(expiry: Optional[str] = None) -> dict:
    """Fetch the raw NSE v3 option-chain JSON.

    Args:
        expiry: optional ``DD-Mon-YYYY`` expiry, e.g. ``"05-May-2026"``.
    """
    url = OPTION_CHAIN_URL
    if expiry:
        url += f"&expiry={expiry}"
    resp = await nse_get(url)
    return resp.json()


async def get_expiry_dates() -> List[str]:
    """List available NIFTY expiry dates.

    Tries the dedicated contract-info endpoint first, then falls back to
    extracting the unique dates from the option chain itself.
    """
    try:
        resp = await nse_get(CONTRACT_INFO_URL)
        if resp.status_code == 200:
            dates = resp.json().get("expiryDates", [])
            if dates:
                return dates
    except Exception as exc:  # noqa: BLE001 - fall through to chain parsing
        log.debug("contract-info expiry fetch failed: %s", exc)

    data = await fetch_option_chain()
    expiries: List[str] = []
    seen: set = set()
    rows = (data.get("records", {}) or {}).get("data", []) or []
    for row in rows:
        # Prefer row-level expiryDate, then CE/PE-level.
        row_expiry = row.get("expiryDate") or ""
        if row_expiry and row_expiry not in seen:
            seen.add(row_expiry)
            expiries.append(row_expiry)
        for side in ("CE", "PE"):
            side_data = row.get(side) or {}
            if isinstance(side_data, dict):
                exp = side_data.get("expiryDate", "")
                if exp and exp not in seen:
                    seen.add(exp)
                    expiries.append(exp)
    return expiries


async def get_nifty_option_chain(
    expiry: Optional[str] = None,
    atm_range: Optional[int] = None,
) -> OptionChain:
    """Fetch and parse the NIFTY option chain.

    Args:
        expiry: optional ``DD-Mon-YYYY`` expiry (default: nearest).
        atm_range: if given, keep only +/- N strikes around ATM.
    """
    data = await fetch_option_chain(expiry)
    chain = parse_option_chain(data)
    if atm_range:
        chain = chain.filter_atm(atm_range)
    return chain
