"""Tests for the provider-oriented connection façades."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataspear.connections import (
    DataConnection,
    GrowwDataConnection,
    NewsConnection,
    NseDataConnection,
)
from dataspear.utils.validation import ConnectionType, IndexRequestParameters


@pytest.mark.asyncio
async def test_legacy_data_connection_keeps_parameters_unchanged():
    params = IndexRequestParameters(suffix="NIFTY", interval=5, data_range=60)
    handler = MagicMock()
    handler.fetch = AsyncMock(return_value=(None, "response"))
    connection = DataConnection(params, request_handler=handler)

    error, response = await connection.fetch()

    assert (error, response) == (None, "response")
    assert params.start_time is None
    assert params.end_time is None


@pytest.mark.asyncio
async def test_nse_connection_delegates_to_shared_session():
    connection = NseDataConnection("https://example.test/api")
    response = object()
    with patch("dataspear.nse.session.nse_get", new=AsyncMock(return_value=response)) as get:
        assert await connection.fetch() is response
    get.assert_awaited_once_with("https://example.test/api")


@pytest.mark.asyncio
async def test_groww_connection_uses_configured_underlying():
    connection = GrowwDataConnection("banknifty")
    with patch(
        "dataspear.groww.fetch_groww_expiries", new=AsyncMock(return_value=["2026-10-08"])
    ) as fetch:
        assert await connection.fetch_expiries() == ["2026-10-08"]
    fetch.assert_awaited_once_with("BANKNIFTY")


@pytest.mark.asyncio
async def test_news_connection_uses_category_query():
    articles = [object()]
    with patch("dataspear.news.fetch_news", new=AsyncMock(return_value=articles)) as fetch:
        result = await NewsConnection(category="market").fetch(days=2)

    assert result == articles
    assert fetch.await_args.kwargs["category"] == "market"
    assert fetch.await_args.kwargs["days"] == 2
