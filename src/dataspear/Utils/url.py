from dataspear.config import config


class URL:
    base_url: str = config.base_url or "https://groww.in"
    api_index_route: str = config.api_index_route or "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/"

    @classmethod
    def get_url(cls, extra: str) -> str:
        return f"{cls.base_url}{cls.api_index_route}{extra}"
