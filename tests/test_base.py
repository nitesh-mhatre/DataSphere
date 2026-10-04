"""The ABC contracts in dataspear.base are enforced for every concrete class."""

import inspect

import pytest

import dataspear
from dataspear import connections, specs, transports
from dataspear.base import BaseConnection, CompositeSpec, RequestSpec, Transport


def _concrete_subclasses(module, base):
    return [
        cls
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if issubclass(cls, base)
        and cls is not base
        and cls.__module__ == module.__name__
        and not cls.__name__.startswith("_")  # internal helpers
    ]


# ── the ABCs themselves cannot be instantiated ───────────────────────────────


@pytest.mark.parametrize("abc_cls", [Transport, RequestSpec, CompositeSpec, BaseConnection])
def test_abstract_bases_cannot_be_instantiated(abc_cls):
    assert inspect.isabstract(abc_cls)
    with pytest.raises(TypeError, match="abstract"):
        abc_cls("x") if abc_cls is Transport else abc_cls()


def test_each_abc_reports_exactly_what_must_be_implemented():
    assert Transport.__abstractmethods__ == {"get"}
    assert RequestSpec.__abstractmethods__ == {"provider", "relative_url"}
    assert CompositeSpec.__abstractmethods__ == {"execute"}  # provider is preset
    assert BaseConnection.__abstractmethods__ == {"provider"}


# ── forgetting a method fails at creation, with a clear message ──────────────


def test_spec_without_provider_or_url_is_rejected():
    class NoProvider(RequestSpec):
        def relative_url(self):
            return "/x"

    class NoUrl(RequestSpec):
        provider = "p"

    for bad in (NoProvider, NoUrl):
        with pytest.raises(TypeError, match="abstract"):
            bad()


def test_minimal_spec_works_with_default_parse():
    class Ok(RequestSpec):
        provider = "p"

        def relative_url(self):
            return "/x"

    spec = Ok()
    assert spec.provider == "p" and spec.relative_url() == "/x"

    class Resp:
        def json(self):
            return {"a": 1}

    assert spec.parse(Resp()) == {"a": 1}


def test_composite_must_implement_execute_and_has_no_url():
    class Missing(CompositeSpec):
        pass

    with pytest.raises(TypeError, match="execute"):
        Missing()

    class Ok(CompositeSpec):
        async def execute(self, core):
            return 1

    assert Ok().provider == "composite"
    with pytest.raises(dataspear.InvalidParametersError):
        Ok().relative_url()


def test_transport_must_implement_get_and_joins_urls():
    class Missing(Transport):
        pass

    with pytest.raises(TypeError, match="get"):
        Missing("https://x.test")

    class Ok(Transport):
        async def get(self, url, **kw):
            return url

    t = Ok("https://x.test/")
    assert t.url("/a?b=1") == "https://x.test/a?b=1"
    assert Ok(lambda: "https://dyn.test/").base_url == "https://dyn.test"


def test_connection_must_declare_provider():
    class Missing(BaseConnection):
        pass

    with pytest.raises(TypeError, match="provider"):
        Missing()


# ── every shipped class honours its contract ─────────────────────────────────


CONCRETE_SPECS = [c for c in _concrete_subclasses(specs, RequestSpec) if not inspect.isabstract(c)]
CONCRETE_TRANSPORTS = _concrete_subclasses(transports, Transport)
CONCRETE_CONNECTIONS = _concrete_subclasses(connections, BaseConnection)


def test_discovery_found_the_shipped_classes():
    assert {c.__name__ for c in CONCRETE_SPECS} >= {  # new specs may be added freely
        "IndexSpec", "GrowwChartSpec", "GrowwOptionChainSpec", "GrowwLivePriceSpec",
        "GrowwOptionChartSpec", "NseOptionChainSpec", "NseExpirySpec", "NseOptionChartSpec",
        "YahooCandlesSpec", "YahooQuoteSpec", "NewsSpec", "LevelsSpec",
    }
    assert {c.__name__ for c in CONCRETE_TRANSPORTS} == {"HttpTransport", "NseTransport"}
    assert {c.__name__ for c in CONCRETE_CONNECTIONS} >= {
        "DataConnection", "IndexDataConnection", "GrowwDataConnection",
        "NseDataConnection", "NewsConnection",
    }


@pytest.mark.parametrize("cls", CONCRETE_SPECS, ids=lambda c: c.__name__)
def test_every_spec_declares_a_provider_string(cls):
    assert isinstance(cls.provider, str) and cls.provider


@pytest.mark.parametrize("cls", CONCRETE_SPECS, ids=lambda c: c.__name__)
def test_every_spec_is_either_single_url_or_composite(cls):
    if issubclass(cls, CompositeSpec):
        assert "execute" in cls.__dict__ or inspect.iscoroutinefunction(cls.execute)
        assert cls.provider == "composite"
    else:
        assert cls.relative_url is not RequestSpec.relative_url
        assert not inspect.isabstract(cls)


@pytest.mark.parametrize("cls", CONCRETE_TRANSPORTS, ids=lambda c: c.__name__)
def test_every_transport_is_concrete(cls):
    assert not inspect.isabstract(cls)
    assert inspect.iscoroutinefunction(cls.get)


@pytest.mark.parametrize("cls", CONCRETE_CONNECTIONS, ids=lambda c: c.__name__)
def test_every_connection_declares_its_provider(cls):
    assert not inspect.isabstract(cls)
    assert cls.provider in {"index", "groww", "nse", "news"}


def test_connection_providers_match_spec_providers():
    spec_providers = {c.provider for c in CONCRETE_SPECS} - {"composite"}
    conn_providers = {c.provider for c in CONCRETE_CONNECTIONS}
    assert conn_providers <= spec_providers


def test_default_core_has_a_transport_for_every_spec_provider():
    core = dataspear.Core.with_defaults()
    needed = {c.provider for c in CONCRETE_SPECS} - {"composite"}
    assert needed <= set(core.providers)
