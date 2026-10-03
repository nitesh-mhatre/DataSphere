"""Provider-oriented asynchronous data connections.

The package also exposes feature-level functions (for example,
``get_nifty_option_chain``).  These small connection objects are useful when
an application wants to configure a source once and perform several requests.
They deliberately keep provider transport details out of analysis modules.
"""

from __future__ import annotations

import time
from copy import copy
from typing import Any, Optional

import httpx

from dataspear.utils.request_handler import RequestHandler
from dataspear.utils.validation import ConnectionType, IndexRequestParameters

__all__ = [
    "DataConnection",
    "IndexDataConnection",
    "GrowwDataConnection",
    "NseDataConnection",
    "NSEDataConnection",
    "NewsConnection",
]


class DataConnection:
    """Backward-compatible base for the legacy Groww index-chart endpoint.

    ``fetch`` returns ``(error, response)`` to preserve the original public
    contract. New provider connections return their provider's parsed model.
    """

    def __init__(
        self,
        params: Optional[IndexRequestParameters] = None,
        request_handler: Optional[RequestHandler] = None,
    ) -> None:
        self.params = params
        self.request_handler = request_handler or RequestHandler()

    async def fetch(
        self, start_time: Optional[int] = None, end_time: Optional[int] = None
    ) -> tuple[Optional[str], Optional[httpx.Response]]:
        """Fetch an index chart without mutating the configured parameters."""
        if self.params is None:
            return "Parameters (`self.params`) must be set before calling fetch().", None

        params = copy(self.params)
        if params.connection_type == ConnectionType.Live:
            current_ms = int(time.time() * 1000)
            params.start_time = current_ms - params.data_range * 60 * 1000
            params.end_time = current_ms
        else:
            if start_time is not None:
                params.start_time = start_time
            if end_time is not None:
                params.end_time = end_time

        params.validate()
        return await self.request_handler.fetch(params)

    async def aclose(self) -> None:
        """Release the pooled HTTP client used by this connection."""
        await self.request_handler.aclose()


class IndexDataConnection(DataConnection):
    """Configured Groww CASH index-chart connection.

    This is the legacy ``DataConnection`` use case, now named for the data it
    actually retrieves. Use :class:`GrowwDataConnection` for other Groww data.
    """

    def __init__(
        self,
        suffix: Optional[str] = None,
        end_time: Optional[int] = None,
        start_time: Optional[int] = None,
        interval: int = 5,
        data_range: int = 60,
        connection_type: ConnectionType = ConnectionType.Live,
        request_handler: Optional[RequestHandler] = None,
    ) -> None:
        params = IndexRequestParameters(
            suffix=suffix,
            end_time=end_time,
            start_time=start_time,
            interval=interval,
            data_range=data_range,
            connection_type=connection_type,
        )
        super().__init__(params=params, request_handler=request_handler)


class NseDataConnection:
    """Connection for arbitrary NSE endpoints using the shared cookie session."""

    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url

    async def fetch(self, url: Optional[str] = None, **kwargs: Any) -> httpx.Response:
        """Fetch an NSE response, including the session warm-up and 403 retry."""
        from dataspear.nse.session import nse_get

        target = url or self.url
        if not target:
            raise ValueError("An NSE endpoint URL must be provided.")
        return await nse_get(target, **kwargs)

    async def fetch_json(self, url: Optional[str] = None, **kwargs: Any) -> Any:
        """Fetch and decode JSON from an NSE endpoint."""
        from dataspear.nse.session import nse_get_json

        target = url or self.url
        if not target:
            raise ValueError("An NSE endpoint URL must be provided.")
        return await nse_get_json(target, **kwargs)


class GrowwDataConnection:
    """Connection façade for Groww charts, options, and live quotes."""

    def __init__(self, underlying: str = "NIFTY") -> None:
        self.underlying = underlying.upper()

    async def fetch_candles(
        self,
        symbol: Optional[str] = None,
        *,
        segment: str = "CASH",
        interval: int = 5,
        data_range: int = 60,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Any:
        from dataspear.groww import fetch_groww_candles

        return await fetch_groww_candles(
            symbol or self.underlying,
            segment=segment,
            interval=interval,
            data_range=data_range,
            start_time=start_time,
            end_time=end_time,
        )

    async def fetch_option_chain(self, expiry: Optional[str] = None) -> Any:
        from dataspear.groww import fetch_groww_option_chain

        return await fetch_groww_option_chain(self.underlying, expiry=expiry)

    async def fetch_expiries(self) -> list[str]:
        from dataspear.groww import fetch_groww_expiries

        return await fetch_groww_expiries(self.underlying)

    async def fetch_live_price(
        self, symbol: str, *, segment: str = "FNO", exchange: str = "NSE"
    ) -> Any:
        from dataspear.groww import fetch_groww_live_price

        return await fetch_groww_live_price(symbol, segment=segment, exchange=exchange)


class NewsConnection:
    """Configured Google News RSS connection for a query or named category."""

    def __init__(self, query: Optional[str] = None, category: str = "market") -> None:
        self.query = query
        self.category = category

    async def fetch(
        self,
        query: Optional[str] = None,
        *,
        category: Optional[str] = None,
        days: int = 1,
        max_results: int = 8,
        fetch_full_content: bool = False,
    ) -> list[Any]:
        """Return scored articles for the configured raw query or category."""
        from dataspear.news import QUERIES, fetch_news

        selected_category = category or self.category
        selected_query = query or self.query or QUERIES.get(selected_category)
        if not selected_query:
            raise ValueError(f"Unknown news category: {selected_category!r}.")
        return await fetch_news(
            selected_query,
            category=selected_category,
            days=days,
            max_results=max_results,
            fetch_full_content=fetch_full_content,
        )


# Initialisms are commonly used in client code; retain the PEP-8 class name as
# the canonical implementation while offering this discoverable alias.
NSEDataConnection = NseDataConnection
