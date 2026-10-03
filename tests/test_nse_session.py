"""Tests for the async NSE session manager."""

import asyncio

import httpx
import pytest

import dataspear.nse.session as session_module
from dataspear.nse.session import NseSession


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "https://www.nseindia.com"),
                response=self,
            )

    def json(self):
        return self._payload


class FakeClient:
    """Fake httpx.AsyncClient. Warmup URLs always succeed; API responses come
    from a shared queue."""

    created = []
    api_responses = []

    def __init__(self, *args, **kwargs):
        self.warmed = []
        self.closed = False
        FakeClient.created.append(self)

    async def get(self, url, **kwargs):
        if url.rstrip("/") in (session_module.NSE_HOME, session_module.NSE_OPTION_CHAIN_PAGE):
            self.warmed.append(url)
            return FakeResponse(200)
        item = FakeClient.api_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        self.closed = True


@pytest.fixture
def patched(monkeypatch):
    FakeClient.created = []
    FakeClient.api_responses = []
    monkeypatch.setattr(session_module.httpx, "AsyncClient", FakeClient)

    async def _noop_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", _noop_sleep)
    return FakeClient


class TestNseSession:
    @pytest.mark.asyncio
    async def test_warmup_and_get_success(self, patched):
        patched.api_responses.append(FakeResponse(200, {"ok": True}))
        session = NseSession()

        resp = await session.get("https://www.nseindia.com/api/test")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        # Warmup hit both pages on the first client.
        assert patched.created[0].warmed == [
            session_module.NSE_HOME,
            session_module.NSE_OPTION_CHAIN_PAGE,
        ]

    @pytest.mark.asyncio
    async def test_reuses_client_between_calls(self, patched):
        patched.api_responses.append(FakeResponse(200, {}))
        patched.api_responses.append(FakeResponse(200, {}))
        session = NseSession()

        await session.get("https://www.nseindia.com/api/a")
        await session.get("https://www.nseindia.com/api/b")

        # Only one client created -> cookies reused.
        assert len(patched.created) == 1

    @pytest.mark.asyncio
    async def test_403_triggers_rewarmup_and_retry(self, patched):
        patched.api_responses.append(FakeResponse(403))
        patched.api_responses.append(FakeResponse(200, {"ok": True}))
        session = NseSession(retry_delay=0)

        resp = await session.get("https://www.nseindia.com/api/test")

        assert resp.status_code == 200
        # A second client was created after the 403.
        assert len(patched.created) == 2
        # Old client was closed.
        assert patched.created[0].closed is True

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(self, patched):
        patched.api_responses.extend([FakeResponse(500), FakeResponse(500), FakeResponse(500)])
        session = NseSession(max_retries=3, retry_delay=0)

        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            await session.get("https://www.nseindia.com/api/test")

    @pytest.mark.asyncio
    async def test_timeout_is_retried(self, patched):
        patched.api_responses.append(httpx.TimeoutException("timed out"))
        patched.api_responses.append(FakeResponse(200, {"ok": True}))
        session = NseSession(retry_delay=0)

        resp = await session.get("https://www.nseindia.com/api/test")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_aclose_closes_client(self, patched):
        session = NseSession()
        await session._warmup()
        client = session._client
        await session.aclose()
        assert client.closed is True
        assert session._client is None
