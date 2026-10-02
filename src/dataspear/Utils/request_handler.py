from dataspear.Utils.url import URL
import httpx
from typing import Optional


class RequestHandler:

    async def fetch(self, extra: str) -> Optional[httpx.Response]:
        url = URL.get_url(extra)
        print(f"Fetching URL: {url}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                print(f"Status: {response.status_code}")
                print(f"Response: {response.text[:500]}")
                return response
        except httpx.RequestError as e:
            print(f"Request error: {e}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"HTTP error: {e.response.status_code} - {e.response.text[:200]}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
