"""Tests for URL module."""
import pytest
from unittest.mock import patch, MagicMock

from dataspear.utils.url import URL
from dataspear.utils.validation import IndexRequestParameters, ConnectionType


class TestURL:
    """Test URL class functionality."""

    def test_get_url_basic(self):
        """Test basic URL generation."""
        with patch.object(URL, 'base_url', 'https://test.com'):
            with patch.object(URL, 'api_index_route', '/api/'):
                url = URL.get_url("endpoint")
                assert url == "https://test.com/api/endpoint"

    def test_get_url_with_query_params(self):
        """Test URL generation with query parameters."""
        with patch.object(URL, 'base_url', 'https://api.example.com'):
            with patch.object(URL, 'api_index_route', '/v1/chart/'):
                extra = "NIFTY?endTimeInMillis=123&intervalInMinutes=5"
                url = URL.get_url(extra)
                assert url == "https://api.example.com/v1/chart/NIFTY?endTimeInMillis=123&intervalInMinutes=5"

    def test_get_url_with_special_characters(self):
        """Test URL generation handles special characters."""
        with patch.object(URL, 'base_url', 'https://test.com'):
            with patch.object(URL, 'api_index_route', '/api/'):
                extra = "symbol?param=value&other=123"
                url = URL.get_url(extra)
                assert "symbol?param=value&other=123" in url

    def test_get_url_returns_string(self):
        """Test that get_url returns a string."""
        with patch.object(URL, 'base_url', 'https://test.com'):
            with patch.object(URL, 'api_index_route', '/api/'):
                result = URL.get_url("test")
                assert isinstance(result, str)

    def test_url_class_attributes_exist(self):
        """Test that URL class has required attributes."""
        assert hasattr(URL, 'base_url')
        assert hasattr(URL, 'api_index_route')
        assert hasattr(URL, 'get_url')

    def test_get_url_from_request_parameters(self):
        """Params must use the API's Millis/Minutes query names, not startTime/endTime."""
        with patch.object(URL, 'base_url', 'https://groww.in'):
            with patch.object(URL, 'api_index_route', '/chart/'):
                params = IndexRequestParameters(
                    suffix='NIFTY',
                    start_time=1782153000000,
                    end_time=1783880980000,
                    interval=5,
                    connection_type=ConnectionType.History,
                )
                url = URL.get_url(params)
                assert 'startTimeInMillis=1782153000000' in url
                assert 'endTimeInMillis=1783880980000' in url
                assert 'intervalInMinutes=5' in url
                assert 'startTime=' not in url
                assert 'endTime=' not in url


class TestURLIntegration:
    """Integration tests for URL generation."""

    def test_full_nifty_url(self):
        """Test generating a full NIFTY chart URL."""
        with patch.object(URL, 'base_url', 'https://groww.in'):
            with patch.object(URL, 'api_index_route', '/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/'):
                extra = "NIFTY?endTimeInMillis=1783880980000&intervalInMinutes=5&startTimeInMillis=1782153000000"
                url = URL.get_url(extra)

                assert url.startswith("https://groww.in")
                assert "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/" in url
                assert "NIFTY?" in url
                assert "endTimeInMillis=1783880980000" in url
                assert "intervalInMinutes=5" in url
                assert "startTimeInMillis=1782153000000" in url
