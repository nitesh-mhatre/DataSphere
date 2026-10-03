"""Async NSE India session.

NSE blocks direct API calls that don't carry a valid browser session cookie.
The working pattern is:

  1. GET https://www.nseindia.com               -> sets nsit / nseappid cookies
  2. GET https://www.nseindia.com/option-chain  -> refreshes the session
  3. Subsequent API calls succeed with those cookies

This module keeps one persistent ``httpx.AsyncClient`` alive and re-warms it
every ``cookie_ttl`` seconds (NSE sessions expire after ~30 min idle). On a
403 the cookies are refreshed and the request is retried.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from dataspear.settings import (
    DEFAULT_HTTP_TIMEOUT,
    NSE_BASE_URL,
    NSE_COOKIE_TTL,
    NSE_HEADERS,
    NSE_MAX_RETRIES,
    NSE_RETRY_DELAY,
)

log = logging.getLogger(__name__)

NSE_HOME = NSE_BASE_URL
NSE_OPTION_CHAIN_PAGE = f"{NSE_BASE_URL}/option-chain"

_HEADERS = NSE_HEADERS

_WARMUP_URLS = [NSE_HOME, NSE_OPTION_CHAIN_PAGE]

_DEFAULT_COOKIE_TTL = NSE_COOKIE_TTL
_DEFAULT_MAX_RETRIES = NSE_MAX_RETRIES
_DEFAULT_RETRY_DELAY = NSE_RETRY_DELAY
_DEFAULT_TIMEOUT = DEFAULT_HTTP_TIMEOUT


class NseSession:
    """Thread/task-safe NSE session with automatic cookie renewal."""

    def __init__(
        self,
        cookie_ttl: float = _DEFAULT_COOKIE_TTL,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay: float = _DEFAULT_RETRY_DELAY,
        timeout: float = _DEFAULT_TIMEOUT,
        headers: Optional[dict] = None,
    ):
        self.cookie_ttl = cookie_ttl
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.headers = {**_HEADERS, **(headers or {})}

        self._client: Optional[httpx.AsyncClient] = None
        self._last_warmup: float = 0.0
        self._lock: Optional[asyncio.Lock] = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_lock(self) -> asyncio.Lock:
        # Created lazily so the session can be instantiated at import time
        # without binding to an event loop.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _needs_warmup(self) -> bool:
        return self._client is None or (time.monotonic() - self._last_warmup) > self.cookie_ttl

    async def _warmup(self) -> None:
        """Create a fresh client and hit the NSE pages to obtain cookies."""
        log.debug("NSE session warmup starting")
        client = httpx.AsyncClient(
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
        )
        for url in _WARMUP_URLS:
            try:
                await client.get(url)
                await asyncio.sleep(0.5)
            except httpx.HTTPError as exc:
                log.warning("NSE warmup request failed for %s: %s", url, exc)

        # Replace the client so stale cookies are dropped.
        old, self._client = self._client, client
        self._last_warmup = time.monotonic()
        if old is not None:
            await old.aclose()

    # ── Public API ────────────────────────────────────────────────────────────

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET ``url`` with managed cookies, retrying on 403/timeout."""
        kwargs.setdefault("timeout", self.timeout)
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries):
            async with self._get_lock():
                if self._needs_warmup():
                    await self._warmup()
                client = self._client

            try:
                resp = await client.get(url, **kwargs)
                if resp.status_code == 403:
                    log.warning(
                        "NSE 403 on %s (attempt %d) - refreshing cookies",
                        url,
                        attempt + 1,
                    )
                    async with self._get_lock():
                        self._last_warmup = 0.0
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue

                resp.raise_for_status()
                return resp

            except httpx.TimeoutException as exc:
                last_exc = exc
                log.warning("Timeout on %s (attempt %d)", url, attempt + 1)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

            except httpx.HTTPError as exc:
                last_exc = exc
                log.warning("Request error %s: %s", url, exc)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

        raise RuntimeError(
            f"NSE API request failed after {self.max_retries} attempts: {url}"
        ) from last_exc

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.get(url, **kwargs)
        return resp.json()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def force_refresh(self) -> None:
        """Force a cookie refresh on the next request."""
        self._last_warmup = 0.0


# ── Module-level singleton ────────────────────────────────────────────────────

_session = NseSession()


async def nse_get(url: str, **kwargs: Any) -> httpx.Response:
    """GET an NSE URL using the shared session. Use this for all NSE calls."""
    return await _session.get(url, **kwargs)


async def nse_get_json(url: str, **kwargs: Any) -> Any:
    return await _session.get_json(url, **kwargs)


def force_refresh() -> None:
    """Force a cookie refresh (call if you start getting 403s mid-session)."""
    _session.force_refresh()


async def aclose() -> None:
    await _session.aclose()
