"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de generieke API-client: retries, back-off, 429/Retry-After,
authenticatie- en responsefouten.
"""

from __future__ import annotations

import aiohttp
import pytest

from custom_components.vun_ev_charge_monitor.api import (
    ApiAuthError,
    ApiClient,
    ApiConnectionError,
    ApiRateLimitedError,
    ApiResponseError,
)


class FakeResponse:
    def __init__(self, status: int, json_data=None, headers: dict | None = None, bad_json=False):
        self.status = status
        self._json_data = json_data
        self.headers = headers or {}
        self._bad_json = bad_json

    async def json(self, content_type=None):
        if self._bad_json:
            raise ValueError("mock malformed json")
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.call_count += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def test_successful_request_returns_json() -> None:
    session = FakeSession([FakeResponse(200, {"ok": True})])
    client = ApiClient(session, max_retries=2, backoff_base_s=0)

    result = await client.async_get_json("https://example.invalid")

    assert result == {"ok": True}
    assert session.call_count == 1


async def test_retries_on_server_error_then_succeeds() -> None:
    session = FakeSession(
        [FakeResponse(503), FakeResponse(503), FakeResponse(200, {"ok": True})]
    )
    client = ApiClient(session, max_retries=2, backoff_base_s=0)

    result = await client.async_get_json("https://example.invalid")

    assert result == {"ok": True}
    assert session.call_count == 3


async def test_server_error_raises_after_max_retries() -> None:
    session = FakeSession([FakeResponse(500), FakeResponse(500), FakeResponse(500)])
    client = ApiClient(session, max_retries=2, backoff_base_s=0)

    with pytest.raises(ApiConnectionError):
        await client.async_get_json("https://example.invalid")

    assert session.call_count == 3


async def test_auth_error_raised_immediately_without_retry() -> None:
    session = FakeSession([FakeResponse(401)])
    client = ApiClient(session, max_retries=3, backoff_base_s=0)

    with pytest.raises(ApiAuthError):
        await client.async_get_json("https://example.invalid")

    assert session.call_count == 1


async def test_rate_limited_respects_retry_after_then_raises() -> None:
    session = FakeSession(
        [
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(429, headers={"Retry-After": "0"}),
        ]
    )
    client = ApiClient(session, max_retries=1, backoff_base_s=0)

    with pytest.raises(ApiRateLimitedError) as exc_info:
        await client.async_get_json("https://example.invalid")

    assert exc_info.value.retry_after == 0.0
    assert session.call_count == 2


async def test_malformed_json_raises_response_error() -> None:
    session = FakeSession([FakeResponse(200, bad_json=True)])
    client = ApiClient(session, max_retries=2, backoff_base_s=0)

    with pytest.raises(ApiResponseError):
        await client.async_get_json("https://example.invalid")


async def test_connection_error_retried_then_raises() -> None:
    session = FakeSession(
        [
            aiohttp.ClientConnectionError("boom"),
            aiohttp.ClientConnectionError("boom"),
        ]
    )
    client = ApiClient(session, max_retries=1, backoff_base_s=0)

    with pytest.raises(ApiConnectionError):
        await client.async_get_json("https://example.invalid")

    assert session.call_count == 2


async def test_unexpected_client_error_status_raises_response_error() -> None:
    session = FakeSession([FakeResponse(404)])
    client = ApiClient(session, max_retries=2, backoff_base_s=0)

    with pytest.raises(ApiResponseError):
        await client.async_get_json("https://example.invalid")

    assert session.call_count == 1
