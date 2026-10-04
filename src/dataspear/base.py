"""Abstract base classes: the contracts every part of dataspear follows.

Read this file first.  There are four building blocks and each is an ABC, so a
subclass that forgets a required method cannot even be created
(``TypeError: Can't instantiate abstract class ...``).

========================  ===========================================  ==========================
Class                     What it is                                   You must implement
========================  ===========================================  ==========================
:class:`Transport`        *How* to reach a provider (base URL + GET)   ``get()``
:class:`RequestSpec`      *What* to fetch from one URL                 ``provider``,
                                                                       ``relative_url()``
:class:`CompositeSpec`    *What* to fetch when it takes several        ``execute()``
                          requests (option chart, levels, ...)
:class:`BaseConnection`   A long-lived, configured provider facade     ``provider``
========================  ===========================================  ==========================

How a request flows::

    spec = GrowwOptionChainSpec("NIFTY")          # a RequestSpec
    chain = await core.fetch(spec)                # Core:
        # 1. transport = core.transport(spec.provider)          -> a Transport
        # 2. url       = transport.url(spec.relative_url())     -> base + relative
        # 3. response  = await transport.get(url)
        # 4. return spec.parse(response)                        -> your model

Adding a new data source = write one ``RequestSpec`` (and one ``Transport`` if
it is a new host).  Nothing in :class:`dataspear.core.Core` changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Union

from dataspear.errors import InvalidParametersError

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from dataspear.core import Core

__all__ = ["Transport", "RequestSpec", "CompositeSpec", "BaseConnection"]


class Transport(ABC):
    """HOW to reach one provider: a base URL and a way to GET a full URL.

    A transport knows nothing about *what* is requested.  Implement
    :meth:`get`; everything else is provided.
    """

    def __init__(self, base_url: Union[str, Callable[[], str]]) -> None:
        # A callable lets the base URL follow configuration changes at runtime.
        self._base_url = base_url

    @property
    def base_url(self) -> str:
        """The provider's base URL without a trailing slash."""
        value = self._base_url() if callable(self._base_url) else self._base_url
        return value.rstrip("/")

    def url(self, relative: str) -> str:
        """Join the base URL and a *relative* path/query into an absolute URL."""
        if relative.startswith(("http://", "https://")):
            raise InvalidParametersError(f"Expected a relative URL, got {relative!r}.")
        return f"{self.base_url}/{relative.lstrip('/')}"

    @abstractmethod
    async def get(self, url: str, **kwargs: Any) -> "httpx.Response":
        """GET an absolute ``url`` and return the HTTP response."""

    async def aclose(self) -> None:
        """Release network resources (default: nothing to release)."""
        return None


class RequestSpec(ABC):
    """WHAT to fetch from a single URL.

    A request object carries its own parameters and answers three questions:

    * ``provider``       - which :class:`Transport` should send me?
    * ``relative_url()`` - what path and query string do I need?
    * ``parse()``        - how do I turn the response into a result?

    Example::

        class FxSpec(RequestSpec):
            provider = "fx"

            def __init__(self, pair="USDINR"):
                self.pair = pair

            def relative_url(self):
                return f"/rates/{self.pair}"

            def parse(self, response):
                return response.json()["rate"]
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """Name of the transport to use (e.g. ``"groww"``).  Set as a class attribute."""

    @abstractmethod
    def relative_url(self) -> str:
        """Path and query string relative to the provider's base URL."""

    def parse(self, response: "httpx.Response") -> Any:
        """Convert the raw HTTP response into the result (default: decoded JSON)."""
        return response.json()

    async def execute(self, core: "Core") -> Any:
        """Fetch through ``core`` and parse.  Rarely overridden; see CompositeSpec."""
        return self.parse(await core.get(self))


class CompositeSpec(RequestSpec):
    """WHAT to fetch when the answer needs several requests.

    A composite has no URL of its own.  Implement :meth:`execute` and fetch the
    parts with ``await core.fetch(other_spec)`` so they share the core's
    transports, timeouts and error handling.
    """

    provider = "composite"

    def relative_url(self) -> str:
        raise InvalidParametersError(
            f"{type(self).__name__} is composite and has no single URL; use core.fetch()."
        )

    @abstractmethod
    async def execute(self, core: "Core") -> Any:
        """Fetch the parts through ``core`` and combine them into one result."""


class BaseConnection(ABC):
    """A long-lived, configured facade for one provider (the original API).

    Connections predate request objects and stay for compatibility.  They share
    the ``provider`` names used by transports and specs, and a common
    :meth:`aclose`.
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name, matching the transport/spec names (e.g. ``"nse"``)."""

    async def aclose(self) -> None:
        """Release resources held by this connection (default: none)."""
        return None
