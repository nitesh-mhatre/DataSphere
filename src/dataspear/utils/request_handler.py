from typing import Optional, Tuple, Union

import httpx

from dataspear.utils.url import URL
from dataspear.utils.validation import IndexRequestParameters


class RequestHandler:
    async def fetch(
        self, extra: Union[IndexRequestParameters, str]
    ) -> Tuple[Optional[str], Optional[httpx.Response]]:
        url = URL.get_url(extra)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
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
