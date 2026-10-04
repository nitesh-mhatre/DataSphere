"""Exceptions raised by the unified request interface."""

from __future__ import annotations

__all__ = [
    "DataSpearError",
    "UnknownProviderError",
    "InvalidParametersError",
]


class DataSpearError(Exception):
    """Base class for errors raised by :class:`dataspear.core.Core`."""


class UnknownProviderError(DataSpearError):
    """A spec asked for a provider/transport the core does not have."""


class InvalidParametersError(DataSpearError):
    """A request spec was built with, or given, invalid parameters."""
