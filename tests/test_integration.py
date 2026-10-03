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
        from dataspear.utils.url import URL
        assert URL is not None

    def test_request_handler_import(self):
        """Test RequestHandler can be imported."""
        from dataspear.utils.request_handler import RequestHandler
        assert RequestHandler is not None


class TestComponentIntegration:
    """Test that components work together."""

    def test_url_uses_config(self):
        """Test that URL class uses config values."""
        from dataspear.config import config
        from dataspear.utils.url import URL

        # Verify URL class references config (now via methods)
        assert hasattr(URL, '_base_url')
        assert hasattr(URL, '_api_index_route')

    def test_full_workflow(self):
        """Test a basic workflow: config -> URL -> handler."""
        from dataspear.config import Config
        from dataspear.utils.url import URL
        from dataspear.utils.request_handler import RequestHandler

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
        """Test config handles missing file gracefully (no error, uses defaults)."""
        from dataspear.config import Config

        config = Config()
        # Missing file should not raise — falls back to system env + defaults.
        config.load_env("/path/that/does/not/exist/.env")
        assert config.base_url == "https://groww.in"
        assert config.api_index_route is not None
        assert config.api_key is None

    def test_url_with_empty_extra(self):
        """Test URL generation with empty extra parameter."""
        from dataspear.utils.url import URL
        import sys

        cfg_mod = sys.modules["dataspear.config"]
        orig = cfg_mod.config
        cfg_mod.config = type(orig)()
        cfg_mod.config.base_url = 'https://test.com'
        cfg_mod.config.api_index_route = '/api/'
        try:
            url = URL.get_url("")
            assert url == "https://test.com/api/"
        finally:
            cfg_mod.config = orig
