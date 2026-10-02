from pathlib import Path
from typing import Optional
from dotenv import dotenv_values


class Config:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url: Optional[str] = None
        self.api_index_route: Optional[str] = None

    def load_env(self, path: str) -> None:
        env_path = Path(path)
        if not env_path.exists():
            raise FileNotFoundError(f"Environment file not found at: {path}")

        env_vars = dotenv_values(env_path)
        self.base_url = env_vars.get("DATASPEAR_BASE_URL", "https://groww.in")
        self.api_index_route = env_vars.get(
            "DATASPEAR_API_INDEX_ROUTE",
            "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/"
        )
        self.api_key = env_vars.get("DATASPEAR_API_KEY")


config = Config()
