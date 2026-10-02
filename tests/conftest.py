"""Pytest configuration and fixtures."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def mock_config():
    """Create a mock config object."""
    from dataspear.config import Config
    config = Config()
    config.base_url = "https://test.example.com"
    config.api_index_route = "/api/v1/"
    config.api_key = "test_api_key"
    return config


@pytest.fixture
def mock_env_file(tmp_path):
    """Create a temporary .env file for testing."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATASPEAR_BASE_URL=https://test.example.com\n"
        "DATASPEAR_API_INDEX_ROUTE=/api/v1/\n"
        "DATASPEAR_API_KEY=test_key_123\n"
    )
    return str(env_file)
