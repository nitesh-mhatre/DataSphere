from typing import Union
import sys

from dataspear.config import DEFAULT_BASE_URL, DEFAULT_API_INDEX_ROUTE
from dataspear.utils.validation import IndexRequestParameters


def _config():
    """Return the current module-level config singleton.

    Reads from sys.modules each call so that tests (and runtime
    load_env()) see the latest object without re-importing url.py.
    """
    return sys.modules["dataspear.config"].config


class URL:
    """URL builder that reads config at call time so load_env() after import works."""

    @classmethod
    def _base_url(cls) -> str:
        return _config().base_url or DEFAULT_BASE_URL

    @classmethod
    def _api_index_route(cls) -> str:
        return _config().api_index_route or DEFAULT_API_INDEX_ROUTE

    @classmethod
    def get_url(cls, extra: Union[IndexRequestParameters, str]) -> str:
        if isinstance(extra, IndexRequestParameters):
            return (
                f"{cls._base_url()}{cls._api_index_route()}{extra.suffix}"
                f"?endTimeInMillis={extra.end_time}"
                f"&intervalInMinutes={extra.interval}"
                f"&startTimeInMillis={extra.start_time}"
            )
        if isinstance(extra, str):
            return f"{cls._base_url()}{cls._api_index_route()}{extra}"
        raise ValueError(
            "Invalid parameter type. Expected IndexRequestParameters instance or str."
        )
