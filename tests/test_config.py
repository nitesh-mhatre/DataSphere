"""Tests for config module."""
import pytest
from pathlib import Path
from unittest.mock import patch

from dataspear.config import Config


class TestConfig:
    """Test Config class functionality."""

    def test_config_init_defaults(self):
        """Test Config initializes with default values."""
        config = Config()
        assert config.api_key is None
        assert config.base_url is None
        assert config.api_index_route is None

    def test_load_env_file_not_found(self):
        """Test that a missing env file falls back to system env + defaults (no error)."""
        config = Config()
        # Should not raise — missing file is handled gracefully.
        config.load_env("/nonexistent/path/.env")
        assert config.base_url == "https://groww.in"
        assert config.api_index_route is not None
        assert config.api_key is None

    def test_load_env_success(self, mock_env_file):
        """Test successful loading of environment variables."""
        config = Config()
        config.load_env(mock_env_file)

        assert config.base_url == "https://test.example.com"
        assert config.api_index_route == "/api/v1/"
        assert config.api_key == "test_key_123"

    def test_load_env_with_defaults(self, tmp_path):
        """Test that defaults are used when env vars are missing."""
        env_file = tmp_path / ".env"
        env_file.write_text("DATASPEAR_API_KEY=my_key\n")

        config = Config()
        config.load_env(str(env_file))

        # Check defaults are applied for missing values
        assert config.base_url == "https://groww.in"  # default from code
        assert config.api_index_route is not None  # has default
        assert config.api_key == "my_key"

    def test_load_env_partial_values(self, tmp_path):
        """Test loading with only some environment variables set."""
        env_file = tmp_path / ".env"
        env_file.write_text("DATASPEAR_BASE_URL=https://custom.url\n")

        config = Config()
        config.load_env(str(env_file))

        assert config.base_url == "https://custom.url"
        assert config.api_key is None  # Not set in env
        assert config.api_index_route is not None  # Has default


class TestConfigSingleton:
    """Test the module-level config singleton."""

    def test_config_singleton_exists(self):
        """Test that the module-level config instance exists."""
        from dataspear.config import config
        assert isinstance(config, Config)
