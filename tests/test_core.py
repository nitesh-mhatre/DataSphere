"""Tests for Core and the request objects it fetches."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from dataspear import (
    Core,
    DataSpearError,
    GrowwChartSpec,
    GrowwLivePriceSpec,
    GrowwOptionChainSpec,
    GrowwOptionChartSpec,
    HttpTransport,
    IndexDataConnection,
    IndexSpec,
    InvalidParametersError,
    LevelsSpec,
    NewsSpec,
    NseExpirySpec,
    NseOptionChainSpec,
    NseOptionChartSpec,
    NseTransport,
    RequestSpec,
    Result,
    Transport,
    UnknownProviderError,
    YahooCandlesSpec,
    YahooQuoteSpec,
    ai_tool_tip,
    as_spec,
)
from dataspear.connections import DataConnection
from dataspear.utils.url import URL
from dataspear.utils.validation import ConnectionType, IndexRequestParameters

from tests.test_groww import SAMPLE_NEXT_DATA, _next_data_html

GROWW = "https://groww.in"
NSE = "https://www.nseindia.com"


class FakeTransport(Transport):
    """Records requested URLs and answers from a ``{url_fragment: payload}`` map."""

    def __init__(self, base_url, routes=None, delay=0.0):
        super().__init__(base_url)
        self.routes = routes or {}
        self.requested: list[str] = []
        self.delay = delay
        self.closed = False

    async def get(self, url, **kwargs):
        self.requested.append(url)
        if self.delay:
            await asyncio.sleep(self.delay)
        for fragment, payload in self.routes.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                if isinstance(payload, str):
                    return httpx.Response(200, text=payload)
                return httpx.Response(200, json=payload)
        raise httpx.HTTPStatusError(
            "404", request=httpx.Request("GET", url), response=httpx.Response(404)
        )

    async def aclose(self):
        self.closed = True


CANDLES = {"candles": [[1790567100, 100, 110, 95, 105, 7], [1790567400, 105, 120, 99, 118, 9]],
           "closingPrice": 118}


def make_core(**routes_by_provider):
    core = Core(timeout=5)
    bases = {"index": GROWW, "groww": GROWW, "nse": NSE,
             "yahoo": "https://query1.finance.yahoo.com", "news": "https://news.google.com"}
    for provider, base in bases.items():
        core.register_transport(provider, FakeTransport(base, routes_by_provider.get(provider)))
    return core


# ── relative URL + base URL join ─────────────────────────────────────────────


def test_defaults_register_every_provider():
    assert Core.with_defaults().providers == ["groww", "index", "news", "nse", "yahoo"]


@pytest.mark.parametrize(
    "spec, expected",
    [
        (GrowwChartSpec("NIFTY", "CASH", 5, start_time=1000, end_time=2000),
         f"{GROWW}/v1/api/charting_service/v2/chart/delayed/exchange/NSE/segment/CASH/NIFTY"
         "?endTimeInMillis=2000&intervalInMinutes=5&startTimeInMillis=1000"),
        (GrowwOptionChainSpec("nifty", "2026-10-06"), f"{GROWW}/options/nifty?expiry=2026-10-06"),
        (GrowwOptionChainSpec("BANKNIFTY"), f"{GROWW}/options/banknifty"),
        (GrowwLivePriceSpec("NIFTY26O0623000CE"),
         f"{GROWW}/v1/api/stocks_fo_data/v1/tr_live_prices/exchange/NSE/segment/FNO/"
         "NIFTY26O0623000CE/latest"),
        (NseOptionChainSpec(), f"{NSE}/api/option-chain-v3?type=Indices&symbol=NIFTY"),
        (NseOptionChainSpec("06-Oct-2026"),
         f"{NSE}/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry=06-Oct-2026"),
        (NseOptionChartSpec("06-Oct-2026", 23000, "pe"),
         f"{NSE}/api/chart-databyindex?index=OPTIDXNIFTY06-10-2026PE23000.00"),
        (YahooCandlesSpec("^NSEI", "1mo", "30m"),
         "https://query1.finance.yahoo.com/v8/finance/chart/^NSEI"
         "?range=1mo&interval=30m&includePrePost=false"),
    ],
)
def test_core_joins_base_and_relative_url(spec, expected):
    assert make_core().url_for(spec) == expected


def test_news_spec_url_uses_category_query():
    url = make_core().url_for(NewsSpec(category="fii_flow"))
    assert url.startswith("https://news.google.com/rss/search?q=FII+buying+OR")
    assert url.endswith("&hl=en-IN&gl=IN&ceid=IN:en")
    with pytest.raises(InvalidParametersError):
        NewsSpec(category="nope")


def test_index_spec_matches_legacy_url_builder_and_follows_config():
    params = IndexRequestParameters(
        suffix="BANKNIFTY", interval=15, start_time=1000, end_time=5000,
        connection_type=ConnectionType.History,
    )
    spec = IndexSpec(params=params)
    core = Core.with_defaults()
    assert core.url_for(spec) == URL.get_url(params)

    from dataspear.config import config

    old = (config.base_url, config.api_index_route)
    config.base_url, config.api_index_route = "https://example.test", "/v9/"
    try:
        assert core.url_for(spec).startswith(
            "https://example.test/v9/BANKNIFTY?endTimeInMillis=5000"
        )
    finally:
        config.base_url, config.api_index_route = old


def test_live_index_spec_resolves_window_when_built_and_leaves_params_alone():
    spec = IndexSpec("NIFTY", interval=5, data_range=60)
    url = make_core().url_for(spec)
    qs = dict(p.split("=") for p in url.split("?")[1].split("&"))
    assert int(qs["endTimeInMillis"]) - int(qs["startTimeInMillis"]) == 60 * 60 * 1000
    assert spec.params.start_time is None and spec.params.end_time is None


def test_invalid_index_parameters_raise_typed_error():
    with pytest.raises(InvalidParametersError):
        IndexSpec("NOPE")
    with pytest.raises(InvalidParametersError):
        IndexSpec("NIFTY", interval=7)


def test_transport_rejects_absolute_relative_url():
    with pytest.raises(InvalidParametersError):
        FakeTransport(GROWW).url("https://evil.test/x")


def test_composite_has_no_url_of_its_own():
    with pytest.raises(InvalidParametersError):
        make_core().url_for(LevelsSpec.groww())


# ── legacy objects are accepted directly ─────────────────────────────────────


def test_as_spec_accepts_legacy_objects():
    params = IndexRequestParameters(suffix="NIFTY")
    assert as_spec(params).params is params
    conn = IndexDataConnection(suffix="INDIAVIX", interval=15)
    assert as_spec(conn).params.suffix == "INDIAVIX"
    spec = GrowwChartSpec()
    assert as_spec(spec) is spec
    with pytest.raises(InvalidParametersError):
        as_spec(DataConnection())
    with pytest.raises(InvalidParametersError):
        as_spec("NIFTY")


async def test_core_fetches_legacy_index_connection_object():
    core = make_core(index={"/chart/delayed/exchange/NSE/segment/CASH/INDIAVIX": CANDLES})
    chart = await core.fetch(IndexDataConnection(suffix="INDIAVIX", interval=15))
    assert chart.symbol == "INDIAVIX" and chart.interval == 15
    assert [c.close for c in chart.candles] == [105.0, 118.0]
    sent = core.transport("index").requested[0]
    assert "intervalInMinutes=15" in sent and "/INDIAVIX?" in sent


async def test_core_fetches_raw_index_request_parameters():
    core = make_core(index={"/NIFTY?": CANDLES})
    chart = await core.fetch(IndexRequestParameters(suffix="NIFTY"))
    assert chart.last_price == 118.0
    raw = await core.fetch(IndexSpec("NIFTY", raw=True))
    assert raw == CANDLES


# ── parsing per provider ─────────────────────────────────────────────────────


async def test_groww_chain_chart_and_live_price():
    core = make_core(groww={
        "/options/nifty": _next_data_html(SAMPLE_NEXT_DATA),
        "/segment/FNO/NIFTY26O0620050CE/latest": {"growwContractId": "NIFTY26O0620050CE",
                                                  "data": {"ltp": 12.5}},
        "/segment/CASH/NIFTY": CANDLES,
    })
    chain = await core.fetch(GrowwOptionChainSpec("NIFTY", "2026-10-06"))
    assert chain.expiry == "2026-10-06" and chain.strikes[0].strike == 20050
    live = await core.fetch(GrowwLivePriceSpec("NIFTY26O0620050CE"))
    assert live.ltp == 12.5
    chart = await core.fetch(GrowwChartSpec("NIFTY"))
    assert len(chart.candles) == 2


async def test_groww_chain_page_without_next_data_is_an_error():
    core = make_core(groww={"/options/": "<html>nothing</html>"})
    result = await core.try_fetch(GrowwOptionChainSpec("NIFTY"))
    assert not result.ok and result.error_type == "RuntimeError"


NSE_CHAIN = {"records": {"underlyingValue": 23010.0, "data": [
    {"strikePrice": 23000, "expiryDate": "06-Oct-2026",
     "CE": {"openInterest": 100, "expiryDate": "06-Oct-2026"},
     "PE": {"openInterest": 300, "expiryDate": "06-Oct-2026"}},
    {"strikePrice": 23050, "expiryDate": "13-Oct-2026",
     "CE": {"openInterest": 50, "expiryDate": "13-Oct-2026"},
     "PE": {"openInterest": 70, "expiryDate": "13-Oct-2026"}},
]}}


async def test_nse_chain_expiries_and_chart():
    core = make_core(nse={
        "/api/option-chain-contract-info": {"expiryDates": ["06-Oct-2026"]},
        "/api/option-chain-v3": NSE_CHAIN,
        "/api/chart-databyindex": {"grapthData": [[1790567100000, 10.5]], "closePrice": 9.0},
    })
    chain = await core.fetch(NseOptionChainSpec())
    assert chain.spot == 23010.0 and len(chain.strikes) == 2
    assert (await core.fetch(NseOptionChainSpec(raw=True)))["records"]["underlyingValue"] == 23010.0
    assert await core.fetch(NseExpirySpec()) == ["06-Oct-2026"]
    chart = await core.fetch(NseOptionChartSpec("06-Oct-2026", 23000, "CE"))
    assert chart.identifier == "OPTIDXNIFTY06-10-2026CE23000.00"
    assert chart.points[0].price == 10.5 and chart.close_price == 9.0


async def test_nse_expiries_fall_back_to_chain():
    core = make_core(nse={
        "/api/option-chain-contract-info": httpx.ConnectError("down"),
        "/api/option-chain-v3": NSE_CHAIN,
    })
    assert await core.fetch(NseExpirySpec()) == ["06-Oct-2026", "13-Oct-2026"]
    requested = core.transport("nse").requested
    assert requested[0].endswith("option-chain-contract-info?symbol=NIFTY")
    assert "option-chain-v3" in requested[1]


async def test_yahoo_candles_and_quote():
    payload = {"chart": {"result": [{
        "meta": {"regularMarketPrice": 15.0, "chartPreviousClose": 10.0},
        "timestamp": [1790567100, 1790567400],
        "indicators": {"quote": [{"open": [1, 2], "high": [3, 4], "low": [0, 1],
                                  "close": [2, 3], "volume": [5, 6]}]},
    }]}}
    core = make_core(yahoo={"/v8/finance/chart/^INDIAVIX": payload, "/v8/finance/chart/^NSEI": payload})
    quote = await core.fetch(YahooQuoteSpec("^INDIAVIX"))
    assert quote == {"price": 15.0, "prev_close": 10.0, "change": 5.0, "change_pct": 50.0}
    candles = await core.fetch(YahooCandlesSpec("^NSEI", "1d", "5m"))
    assert [c.close for c in candles] == [2.0, 3.0]


async def test_news_spec_parses_and_scores():
    rss = """<rss><channel>
      <item><title>Nifty rally on strong inflows</title><link>http://a</link>
      <source>X</source></item>
      <item><title>Nifty rally on strong inflows</title><link>http://dup</link></item>
      <item><title>RBI hikes repo rate</title><link>http://b</link></item>
    </channel></rss>"""
    core = make_core(news={"/rss/search": rss})
    articles = await core.fetch(NewsSpec(category="market", max_results=5))
    assert [a.title for a in articles] == ["Nifty rally on strong inflows", "RBI hikes repo rate"]
    assert articles[0].category == "market"


# ── composite specs ──────────────────────────────────────────────────────────


async def test_option_chart_resolves_contract_then_falls_back_to_nse():
    core = make_core(
        groww={"/options/nifty": _next_data_html(SAMPLE_NEXT_DATA),
               "/segment/FNO/NIFTY26O0620050CE": {"candles": []}},
        nse={"/api/chart-databyindex": {"grapthData": [[1790567100000, 7.0]], "closePrice": 6.0}},
    )
    chart = await core.fetch(GrowwOptionChartSpec("2026-10-06", 20050, "CE"))
    assert chart.source == "nse" and chart.symbol == "NIFTY26O0620050CE"
    assert chart.candles[0].close == 7.0
    assert "/segment/FNO/NIFTY26O0620050CE" in core.transport("groww").requested[1]
    assert "OPTIDXNIFTY06-10-2026CE20050.00" in core.transport("nse").requested[0]


async def test_option_chart_without_fallback_or_with_groww_data():
    fno = {"candles": [[1790567100, 1, 2, 1, 2, 3]]}
    core = make_core(groww={"/options/nifty": _next_data_html(SAMPLE_NEXT_DATA),
                            "/segment/FNO/": fno})
    chart = await core.fetch(GrowwOptionChartSpec("2026-10-06", 20050, "CE"))
    assert chart.candles and core.transport("nse").requested == []

    empty = make_core(groww={"/options/nifty": _next_data_html(SAMPLE_NEXT_DATA),
                             "/segment/FNO/": {"candles": []}})
    chart = await empty.fetch(GrowwOptionChartSpec("2026-10-06", 20050, "CE", fallback_nse=False))
    assert chart.candles == [] and empty.transport("nse").requested == []


async def test_option_chart_unknown_strike_raises():
    core = make_core(groww={"/options/nifty": _next_data_html(SAMPLE_NEXT_DATA)})
    result = await core.try_fetch(GrowwOptionChartSpec("2026-10-06", 99999, "CE"))
    assert not result.ok and result.error_type == "ValueError"


def _trending(n=40):
    rows = []
    for i in range(n):
        base = 23000 + (i % 8) * 20
        rows.append([1790567100 + i * 300, base, base + 15, base - 15, base + 5, 100 + i])
    return {"candles": rows}


async def test_levels_spec_fetches_intraday_and_daily_through_core():
    core = make_core(groww={"/segment/CASH/NIFTY": _trending()})
    levels = await core.fetch(LevelsSpec.groww("NIFTY"))
    assert hasattr(levels, "to_dict")
    requested = core.transport("groww").requested
    assert len(requested) == 2
    assert any("intervalInMinutes=5" in u for u in requested)
    assert any("intervalInMinutes=1440" in u for u in requested)


async def test_levels_spec_tolerates_failed_optional_daily_series():
    class Flaky(FakeTransport):
        async def get(self, url, **kw):
            if "intervalInMinutes=1440" in url:
                raise httpx.ConnectError("nope")
            return await super().get(url, **kw)

    core = make_core()
    core.register_transport("groww", Flaky(GROWW, {"/segment/CASH/NIFTY": _trending()}), replace=True)
    assert (await core.try_fetch(LevelsSpec.groww("NIFTY"))).ok


async def test_levels_spec_from_yahoo_and_validation():
    payload = {"chart": {"result": [{"meta": {}, "timestamp": [1790567100 + i * 1800 for i in range(30)],
               "indicators": {"quote": [{k: [23000 + (i % 6) * 10 for i in range(30)]
                                         for k in ("open", "high", "low", "close", "volume")}]}}]}}
    core = make_core(yahoo={"/v8/finance/chart/": payload})
    assert (await core.try_fetch(LevelsSpec.yahoo("^NSEI"))).ok
    with pytest.raises(InvalidParametersError):
        LevelsSpec([])


# ── Core behaviour ───────────────────────────────────────────────────────────


async def test_fetch_raises_and_try_fetch_wraps():
    core = make_core()
    with pytest.raises(httpx.HTTPStatusError):
        await core.fetch(GrowwChartSpec())
    result = await core.try_fetch(GrowwChartSpec())
    assert isinstance(result, Result) and not result.ok
    assert result.error_type == "HTTPStatusError" and result.spec == "GrowwChartSpec"
    with pytest.raises(DataSpearError, match="GrowwChartSpec failed"):
        result.unwrap()


async def test_unknown_provider_is_a_typed_error():
    class Mystery(RequestSpec):
        provider = "mystery"

        def relative_url(self):
            return "/x"

    core = make_core()
    with pytest.raises(UnknownProviderError, match="groww"):
        await core.fetch(Mystery())
    assert (await core.try_fetch(Mystery())).error_type == "UnknownProviderError"


async def test_custom_spec_and_transport_plug_in_without_touching_core():
    class FxSpec(RequestSpec):
        provider = "fx"

        def __init__(self, pair):
            self.pair = pair

        def relative_url(self):
            return f"/rates/{self.pair}"

        def parse(self, response):
            return response.json()["rate"]

    core = make_core()
    core.register_transport("fx", FakeTransport("https://fx.test/", {"/rates/USDINR": {"rate": 83.1}}))
    assert await core.fetch(FxSpec("USDINR")) == 83.1
    assert core.transport("fx").requested == ["https://fx.test/rates/USDINR"]
    with pytest.raises(ValueError):
        core.register_transport("fx", FakeTransport("x"))
    with pytest.raises(TypeError):
        core.register_transport("bad", object())


async def test_fetch_many_mixes_providers_concurrently_and_keeps_order():
    core = Core(timeout=5)
    core.register_transport("groww", FakeTransport(GROWW, {"/segment/CASH/": CANDLES}, delay=0.2))
    core.register_transport("nse", FakeTransport(NSE, {"/api/option-chain-v3": NSE_CHAIN}, delay=0.2))
    loop = asyncio.get_running_loop()
    start = loop.time()
    results = await core.fetch_many(
        [GrowwChartSpec(), NseOptionChainSpec(), YahooQuoteSpec(), GrowwChartSpec("BANKNIFTY")]
    )
    assert loop.time() - start < 0.5
    assert [r.ok for r in results] == [True, True, False, True]
    assert results[2].error_type == "UnknownProviderError"
    assert results[0].data.symbol == "NIFTY" and results[3].data.symbol == "BANKNIFTY"
    assert all(isinstance(r.to_dict()["elapsed_ms"], float) for r in results)


async def test_fetch_many_respects_max_concurrency():
    core = Core(timeout=5, max_concurrency=1)
    core.register_transport("groww", FakeTransport(GROWW, {"/segment/CASH/": CANDLES}, delay=0.1))
    loop = asyncio.get_running_loop()
    start = loop.time()
    await core.fetch_many([GrowwChartSpec()] * 3)
    assert loop.time() - start >= 0.29


async def test_timeouts_default_and_per_call():
    core = Core(timeout=0.05)
    core.register_transport("groww", FakeTransport(GROWW, {"/segment/": CANDLES}, delay=0.5))
    result = await core.try_fetch(GrowwChartSpec())
    assert result.error_type == "TimeoutError" and "GrowwChartSpec" in result.error
    assert (await core.try_fetch(GrowwChartSpec(), timeout=2)).ok


async def test_result_to_dict_serialises_models():
    core = make_core(groww={"/segment/": CANDLES})
    out = (await core.try_fetch(GrowwChartSpec())).to_dict()
    json.dumps(out)  # must be JSON-serialisable
    assert out["ok"] and out["data"]["candles"][0]["close"] == 105.0


async def test_aclose_closes_every_transport():
    core = make_core()
    async with core:
        pass
    assert all(core.transport(p).closed for p in core.providers)


# ── real transports ──────────────────────────────────────────────────────────


async def test_http_transport_gets_and_raises_for_status():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200 if "ok" in request.url.path else 500, json={"v": 1})

    transport = HttpTransport("https://api.test/")
    transport._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    core = Core(transports={"t": transport})

    class S(RequestSpec):
        provider = "t"

        def __init__(self, path):
            self.path = path

        def relative_url(self):
            return self.path

    assert await core.fetch(S("/ok?a=1")) == {"v": 1}
    assert seen == ["https://api.test/ok?a=1"]
    with pytest.raises(httpx.HTTPStatusError):
        await core.fetch(S("/bad"))
    await core.aclose()
    assert transport._client is None


async def test_nse_transport_uses_cookie_session_not_plain_http():
    session = type("S", (), {})()
    session.get = AsyncMock(return_value=httpx.Response(200, json=NSE_CHAIN))
    session.aclose = AsyncMock()
    core = Core(transports={"nse": NseTransport(session=session)})
    chain = await core.fetch(NseOptionChainSpec("06-Oct-2026"))
    assert chain.spot == 23010.0
    session.get.assert_awaited_once_with(
        f"{NSE}/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry=06-Oct-2026"
    )
    await core.aclose()
    session.aclose.assert_awaited_once()


# ── AI catalog ───────────────────────────────────────────────────────────────


def test_ai_tool_tip_documents_request_objects():
    prompt, tools = ai_tool_tip()
    assert "UNIFIED REQUESTS" in prompt and "core.fetch(IndexSpec" in prompt
    assert {"Core", "RequestSpec", "IndexSpec", "LevelsSpec", "GrowwOptionChartSpec"} <= set(tools)
    assert "get_nifty_option_chain(" in prompt
    assert "Required:" in prompt and "Optional:" in prompt
    assert callable(tools["get_nifty_option_chain"])
    assert callable(tools["IndexSpec"])
    assert tools["URL.get_url"]("NIFTY").startswith("http")
    assert "NSE_HOLIDAYS" not in tools
