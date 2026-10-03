from typing import Optional, Tuple, Union

import httpx

from dataspear.settings import DEFAULT_HTTP_TIMEOUT, JSON_HEADERS
from dataspear.utils.url import URL
from dataspear.utils.validation import IndexRequestParameters


class RequestHandler:
    """Reusable async HTTP getter with one shared client for connection pooling.

    Close with ``await handler.aclose()`` when done (e.g. at process exit).
    """

    def __init__(
        self, timeout: float = DEFAULT_HTTP_TIMEOUT, headers: Optional[dict] = None
    ):
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout
        self._headers = dict(headers or JSON_HEADERS)

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
