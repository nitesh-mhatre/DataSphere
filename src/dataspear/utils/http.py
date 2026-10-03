"""Small shared helpers for one-shot asynchronous HTTP requests."""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from dataspear.settings import DEFAULT_HTTP_TIMEOUT


async def get_response(
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> httpx.Response:
    """Make a redirected GET request and return its successful response.

    This helper intentionally leaves error handling to each feature module so
    callers can preserve their own fallback and logging behavior.
    """
    async with httpx.AsyncClient(
        headers=dict(headers or {}), timeout=timeout, follow_redirects=True
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response


async def get_json(
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> Any:
    """Make a GET request and decode its JSON response."""
    response = await get_response(url, params=params, headers=headers, timeout=timeout)
    return response.json()


async def get_text(
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> str:
    """Make a GET request and return its text body."""
    response = await get_response(url, params=params, headers=headers, timeout=timeout)
    return response.text
