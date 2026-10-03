from typing import Optional, Tuple, Union

import httpx

from dataspear.utils.url import URL
from dataspear.utils.validation import IndexRequestParameters


class RequestHandler:
    """Reusable async HTTP getter with one shared client for connection pooling.

    Close with ``await handler.aclose()`` when done (e.g. at process exit).
    """

    def __init__(self, timeout: float = 15.0, headers: Optional[dict] = None):
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout
        self._headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }

    def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers, timeout=self._timeout, follow_redirects=True
            )
        return self._client

    async def fetch(
        self, extra: Union[IndexRequestParameters, str]
    ) -> Tuple[Optional[str], Optional[httpx.Response]]:
        url = URL.get_url(extra)
        try:
            response = await self._client_instance().get(url)
            response.raise_for_status()
            return None, response
        except httpx.RequestError as e:
            return f"Request error: {e}", None
        except httpx.HTTPStatusError as e:
            return (
                f"HTTP error: {e.response.status_code} - {e.response.text[:200]}",
                None,
            )
        except Exception as e:
            return f"Unexpected error: {e}", None

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
