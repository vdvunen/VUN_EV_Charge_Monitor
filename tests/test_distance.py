"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de optionele rijafstand-verrijking (OpenRouteService Matrix API).
Faalt nooit hard — elke fout valt terug op de ongewijzigde (hemelsbrede)
invoer, zie moduledocstring in distance.py.
"""

from __future__ import annotations

from homeassistant.util import dt as dt_util

from custom_components.vun_ev_charge_monitor.api import (
    ApiAuthError,
    ApiConnectionError,
    ApiRateLimitedError,
    ApiResponseError,
)
from custom_components.vun_ev_charge_monitor.distance import async_enrich_with_driving_distance
from custom_components.vun_ev_charge_monitor.models import (
    ChargeLocation,
    ChargePointStatus,
    DataQuality,
    Evse,
)


class FakeApiClient:
    def __init__(self, payload=None, exception: Exception | None = None) -> None:
        self._payload = payload
        self._exception = exception
        self.last_json_body: dict | None = None

    async def async_post_json(self, url, json_body=None, headers=None):
        self.last_json_body = json_body
        if self._exception:
            raise self._exception
        return self._payload


def _location(name: str, lat: float, lon: float, distance_m: float) -> ChargeLocation:
    return ChargeLocation(
        provider="ndw",
        provider_location_id=name,
        external_id=None,
        name=name,
        latitude=lat,
        longitude=lon,
        address=None,
        postal_code=None,
        city=None,
        country="NL",
        operator="Test",
        distance_m=distance_m,
        navigation_url="https://example.invalid",
        evses=(Evse(evse_id=f"{name}-1", status=ChargePointStatus.AVAILABLE, connectors=()),),
        realtime_data_available=True,
        provider_status_raw=None,
        last_status_update=dt_util.utcnow(),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME,
    )


async def test_empty_locations_returns_empty() -> None:
    client = FakeApiClient(payload={})
    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=()
    )
    assert result == ()


async def test_successful_enrichment_replaces_distance() -> None:
    locations = (
        _location("A", 52.01, 5.01, 100.0),
        _location("B", 52.02, 5.02, 200.0),
    )
    client = FakeApiClient(payload={"distances": [[350.0, 420.0]]})

    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result[0].distance_m == 350.0
    assert result[0].distance_is_driving is True
    assert result[1].distance_m == 420.0
    assert result[1].distance_is_driving is True


async def test_request_body_uses_lon_lat_order_and_origin_as_source() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0),)
    client = FakeApiClient(payload={"distances": [[300.0]]})

    await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    body = client.last_json_body
    assert body["locations"][0] == [5.0, 52.0]  # origin: [lon, lat]
    assert body["locations"][1] == [5.01, 52.01]  # locatie: [lon, lat]
    assert body["sources"] == [0]
    assert body["destinations"] == [1]
    assert body["metrics"] == ["distance"]
    assert body["units"] == "m"


async def test_auth_error_falls_back_to_original() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0),)
    client = FakeApiClient(exception=ApiAuthError("invalid key"))

    result = await async_enrich_with_driving_distance(
        client, "bad-key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result == locations
    assert result[0].distance_is_driving is False


async def test_rate_limited_falls_back_to_original() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0),)
    client = FakeApiClient(exception=ApiRateLimitedError("slow down"))

    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result == locations


async def test_connection_error_falls_back_to_original() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0),)
    client = FakeApiClient(exception=ApiConnectionError("down"))

    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result == locations


async def test_malformed_response_falls_back_to_original() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0),)
    client = FakeApiClient(exception=ApiResponseError("bad json"))

    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result == locations


async def test_missing_distances_key_falls_back_to_original() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0),)
    client = FakeApiClient(payload={"durations": [[42.0]]})

    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result == locations


async def test_wrong_length_distances_falls_back_to_original() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0), _location("B", 52.02, 5.02, 200.0))
    client = FakeApiClient(payload={"distances": [[350.0]]})  # slechts 1 i.p.v. 2

    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result == locations


async def test_null_distance_for_one_location_keeps_its_original_distance() -> None:
    locations = (_location("A", 52.01, 5.01, 100.0), _location("B", 52.02, 5.02, 200.0))
    client = FakeApiClient(payload={"distances": [[350.0, None]]})

    result = await async_enrich_with_driving_distance(
        client, "key", origin_lat=52.0, origin_lon=5.0, locations=locations
    )

    assert result[0].distance_m == 350.0
    assert result[0].distance_is_driving is True
    assert result[1].distance_m == 200.0  # onveranderd, geen route gevonden
    assert result[1].distance_is_driving is False
