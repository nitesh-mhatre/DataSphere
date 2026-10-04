"""Package-wide defaults and environment-backed settings.

Service modules import shared HTTP defaults from here. ``Config`` and
``config`` are the established public names for the Groww chart endpoint and
remain re-exported by :mod:`dataspear.config`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

GROWW_BASE_URL = "https://groww.in"
NSE_BASE_URL = "https://www.nseindia.com"
YAHOO_BASE_URL = "https://query1.finance.yahoo.com"
GOOGLE_NEWS_BASE_URL = "https://news.google.com"
YAHOO_CHART_ENDPOINT = f"{YAHOO_BASE_URL}/v8/finance/chart/{{ticker}}"
GOOGLE_NEWS_RSS_ENDPOINT = (
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)
DEFAULT_BASE_URL = GROWW_BASE_URL
DEFAULT_API_INDEX_ROUTE = (
    "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HTTP_TIMEOUT = 15.0
GROWW_HTTP_TIMEOUT = 20.0
NEWS_ARTICLE_TIMEOUT = 10.0
NSE_COOKIE_TTL = 25 * 60
NSE_MAX_RETRIES = 3
NSE_RETRY_DELAY = 2.0

JSON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
}
GROWW_HEADERS = {
    **JSON_HEADERS,
    "Accept-Language": "en-US,en;q=0.9",
    # Some Python/httpx combinations fail while decoding brotli responses.
    "Accept-Encoding": "gzip, deflate",
}
NSE_HEADERS = {
    **GROWW_HEADERS,
    "Referer": f"{NSE_BASE_URL}/option-chain",
    "Origin": NSE_BASE_URL,
    "Connection": "keep-alive",
    "DNT": "1",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}
NEWS_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


class Config:
    """Environment-backed endpoint settings, loaded explicitly by consumers."""

    def __init__(self) -> None:
        self.api_key: Optional[str] = None
        self.base_url: Optional[str] = None
        self.api_index_route: Optional[str] = None

    def load_env(self, path: str = ".env") -> None:
        """Load settings from ``path`` with environment variables taking priority."""
        env_path = Path(path)
        env_vars = dotenv_values(env_path) if env_path.exists() else {}

        self.base_url = (
            env_vars.get("DATASPEAR_BASE_URL")
            or os.getenv("DATASPEAR_BASE_URL")
            or DEFAULT_BASE_URL
        )
        self.api_index_route = (
            env_vars.get("DATASPEAR_API_INDEX_ROUTE")
            or os.getenv("DATASPEAR_API_INDEX_ROUTE")
            or DEFAULT_API_INDEX_ROUTE
        )
        self.api_key = env_vars.get("DATASPEAR_API_KEY") or os.getenv("DATASPEAR_API_KEY")


# Descriptive alias for new code; ``Config`` remains the established name.
Settings = Config
config = Config()

__all__ = [
    "Config",
    "Settings",
    "config",
    "DEFAULT_BASE_URL",
    "DEFAULT_API_INDEX_ROUTE",
    "GROWW_BASE_URL",
    "NSE_BASE_URL",
    "YAHOO_BASE_URL",
    "GOOGLE_NEWS_BASE_URL",
    "YAHOO_CHART_ENDPOINT",
    "GOOGLE_NEWS_RSS_ENDPOINT",
    "USER_AGENT",
    "DEFAULT_HTTP_TIMEOUT",
    "GROWW_HTTP_TIMEOUT",
    "NEWS_ARTICLE_TIMEOUT",
    "NSE_COOKIE_TTL",
    "NSE_MAX_RETRIES",
    "NSE_RETRY_DELAY",
    "JSON_HEADERS",
    "GROWW_HEADERS",
    "NSE_HEADERS",
    "NEWS_HEADERS",
]

