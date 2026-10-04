"""Concrete :class:`~dataspear.base.Transport` implementations."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Union

import httpx

from dataspear.base import Transport
from dataspear.settings import DEFAULT_HTTP_TIMEOUT, JSON_HEADERS, NSE_BASE_URL

__all__ = ["HttpTransport", "NseTransport"]


class HttpTransport(Transport):
    """Plain pooled HTTP GETs; raises ``httpx.HTTPStatusError`` on 4xx/5xx."""

    def __init__(
        self,
        base_url: Union[str, Callable[[], str]],
        headers: Optional[Mapping[str, str]] = None,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
    ) -> None:
        super().__init__(base_url)
        self._headers = dict(headers or JSON_HEADERS)
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers, timeout=self._timeout, follow_redirects=True
            )
        return self._client

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        response = await self._client_instance().get(url, **kwargs)
        response.raise_for_status()
        return response

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None


class NseTransport(Transport):
    """NSE GETs through a cookie-managed :class:`NseSession` (warm-up, 403 retry).

    Uses its own session by default so closing one Core never affects the
    package-level shared NSE session.
    """

    def __init__(self, base_url: str = NSE_BASE_URL, session: Any = None) -> None:
        super().__init__(base_url)
        if session is None:
            from dataspear.nse.session import NseSession

            session = NseSession()
        self.session = session

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.session.get(url, **kwargs)

    async def aclose(self) -> None:
        await self.session.aclose()
