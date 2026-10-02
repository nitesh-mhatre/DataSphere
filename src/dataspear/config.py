from pathlib import Path
from typing import Optional
from dotenv import dotenv_values
import configparser

class Config:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url: Optional[str] = None
        self.api_index_route: Optional[str] = None

    def load_env(self, path: str) -> None:
        env_path = Path(path)
        if not env_path.exists():
            raise FileNotFoundError(f"Environment file not found at: {path}")

        config = configparser.ConfigParser()
        config.read(path)


        self.base_url = config.get("DEFAULT", "DATASPEAR_BASE_URL", fallback="https://groww.in")
        self.api_index_route = config.get(
            "DEFAULT",
            "DATASPEAR_API_INDEX_ROUTE",
            "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/"
        )

config = Config()
