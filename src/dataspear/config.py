from pathlib import Path
from typing import Optional

import os
from dotenv import dotenv_values

DEFAULT_BASE_URL = "https://groww.in"
DEFAULT_API_INDEX_ROUTE = (
    "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/"
)


class Config:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url: Optional[str] = None
        self.api_index_route: Optional[str] = None

    def load_env(self, path: str = ".env") -> None:
        """Load settings from a .env file (optional — system env vars always win).

        When ``path`` is omitted or the file is missing, falls back to system
        environment variables and then the built-in defaults, so a consumer can
        call ``config.load_env()`` without shipping a .env file.
        """
        env_path = Path(path)
        if env_path.exists():
            env_vars = dotenv_values(env_path)
        else:
            env_vars = {}

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
        self.api_key = (
            env_vars.get("DATASPEAR_API_KEY")
            or os.getenv("DATASPEAR_API_KEY")
        )


config = Config()
