from dataspear.config import config
from dataspear.utils.validation import IndexRequestParameters, ConnectionType

class URL:
    base_url: str = config.base_url or "https://groww.in"
    api_index_route: str = config.api_index_route or "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/"

    @classmethod
    def get_url(cls, extra : IndexRequestParameters) -> str:
        if isinstance(extra, IndexRequestParameters):
            return f"{cls.base_url}{cls.api_index_route}{extra.suffix}?startTime={extra.start_time}&endTime={extra.end_time}&interval={extra.interval}"
        else:
            raise ValueError("Invalid parameter type. Expected IndexRequestParameters instance.")