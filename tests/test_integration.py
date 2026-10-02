"""Integration tests for the DataSpear package."""
import pytest
from unittest.mock import patch

# Note: These are basic integration tests that verify components work together


class TestModuleImports:
    """Test that all modules can be imported correctly."""

    def test_config_import(self):
        """Test config module can be imported."""
        from dataspear.config import Config, config
        assert Config is not None
        assert config is not None

    def test_url_import(self):
        """Test URL module can be imported."""
        from dataspear.Utils.url import URL
        assert URL is not None

    def test_request_handler_import(self):
        """Test RequestHandler can be imported."""
        from dataspear.Utils.request_handler import RequestHandler
        assert RequestHandler is not None


class TestComponentIntegration:
    """Test that components work together."""

    def test_url_uses_config(self):
        """Test that URL class uses config values."""
        from dataspear.config import config
        from dataspear.Utils.url import URL

        # Verify URL class references config
        assert hasattr(URL, 'base_url')
        assert hasattr(URL, 'api_index_route')

    def test_full_workflow(self):
        """Test a basic workflow: config -> URL -> handler."""
        from dataspear.config import Config
        from dataspear.Utils.url import URL
        from dataspear.Utils.request_handler import RequestHandler

        # Generate URL using module-level config
        test_url = URL.get_url("endpoint?param=value")

        # Verify URL structure (uses default config values)
        assert test_url.startswith("https://groww.in")  # default base_url
        assert "/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/endpoint?param=value" in test_url

        # Handler can be instantiated
        handler = RequestHandler()
        assert handler is not None


class TestErrorHandling:
    """Test error handling across components."""

    def test_config_missing_file(self):
        """Test config handles missing file gracefully."""
        from dataspear.config import Config

        config = Config()
        with pytest.raises(FileNotFoundError):
            config.load_env("/path/that/does/not/exist/.env")

    def test_url_with_empty_extra(self):
        """Test URL generation with empty extra parameter."""
        from dataspear.Utils.url import URL

        with patch.object(URL, 'base_url', 'https://test.com'):
            with patch.object(URL, 'api_index_route', '/api/'):
                url = URL.get_url("")
                assert url == "https://test.com/api/"
