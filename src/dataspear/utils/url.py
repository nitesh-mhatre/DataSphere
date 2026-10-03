from typing import Union

from dataspear.config import config, DEFAULT_BASE_URL, DEFAULT_API_INDEX_ROUTE
from dataspear.utils.validation import IndexRequestParameters


class URL:
    base_url: str = config.base_url or DEFAULT_BASE_URL
    api_index_route: str = config.api_index_route or DEFAULT_API_INDEX_ROUTE

    @classmethod
    def get_url(cls, extra: Union[IndexRequestParameters, str]) -> str:
        if isinstance(extra, IndexRequestParameters):
            return (
                f"{cls.base_url}{cls.api_index_route}{extra.suffix}"
                f"?endTimeInMillis={extra.end_time}"
                f"&intervalInMinutes={extra.interval}"
                f"&startTimeInMillis={extra.start_time}"
            )
        if isinstance(extra, str):
            return f"{cls.base_url}{cls.api_index_route}{extra}"
        raise ValueError(
            "Invalid parameter type. Expected IndexRequestParameters instance or str."
        )
