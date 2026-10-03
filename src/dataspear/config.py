"""Backward-compatible import path for package settings."""

from dataspear.settings import (
    DEFAULT_API_INDEX_ROUTE,
    DEFAULT_BASE_URL,
    Config,
    Settings,
    config,
)

__all__ = ["Config", "Settings", "config", "DEFAULT_BASE_URL", "DEFAULT_API_INDEX_ROUTE"]
