"""Tests for request handler module."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from dataspear.Utils.request_handler import RequestHandler


class TestRequestHandler:
    """Test RequestHandler class functionality."""

    def test_handler_instantiation(self):
        """Test that RequestHandler can be instantiated."""
        handler = RequestHandler()
        assert handler is not None

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Test successful fetch operation."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = '{"data": "success"}'
        mock_response.headers = {"content-type": "application/json"}
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            handler = RequestHandler()
            result = await handler.fetch("test_endpoint")

            assert result is not None
            assert result.status_code == 200
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_http_error(self):
        """Test fetch handles HTTP errors gracefully."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.text = '{"error": "not found"}'
        mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        ))

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            handler = RequestHandler()
            result = await handler.fetch("nonexistent_endpoint")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_request_error(self):
        """Test fetch handles network errors gracefully."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
            mock_client_class.return_value = mock_client

            handler = RequestHandler()
            result = await handler.fetch("test_endpoint")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_failure(self):
        """Test that fetch returns None on any error."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("Unexpected error"))
            mock_client_class.return_value = mock_client

            handler = RequestHandler()
            result = await handler.fetch("test_endpoint")

            assert result is None


class TestRequestHandlerIntegration:
    """Integration tests for RequestHandler."""

    @pytest.mark.asyncio
    async def test_fetch_builds_correct_url(self):
        """Test that fetch builds the correct URL."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = '{"test": true}'
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            handler = RequestHandler()
            await handler.fetch("NIFTY?test=123")

            # Verify the client was called
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            url = call_args[0][0] if call_args[0] else call_args[1].get('url')

            assert url is not None
            assert "NIFTY?test=123" in url
