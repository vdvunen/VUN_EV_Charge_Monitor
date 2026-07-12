"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de providers (NDW, TomTom, Open Charge Map): normalisatie,
connectormapping, ongeldige-recordafhandeling en foutvertaling.
"""

from __future__ import annotations

import pytest

from custom_components.vun_ev_charge_monitor.api import (
    ApiAuthError,
    ApiConnectionError,
    ApiRateLimitedError,
)
from custom_components.vun_ev_charge_monitor.models import (
    ChargePointStatus,
    ConnectorType,
    DataQuality,
)
from custom_components.vun_ev_charge_monitor.providers.base import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitedError,
)
from custom_components.vun_ev_charge_monitor.providers.ndw import NdwProvider
from custom_components.vun_ev_charge_monitor.providers.open_charge_map import OpenChargeMapProvider
from custom_components.vun_ev_charge_monitor.providers.tomtom import TomTomProvider

_ORIGIN_LAT = 52.3702
_ORIGIN_LON = 4.8952


class FakeApiClient:
    def __init__(self, payload=None, exception: Exception | None = None) -> None:
        self._payload = payload
        self._exception = exception

    async def async_get_json(self, url, params=None, headers=None):
        if self._exception:
            raise self._exception
        return self._payload


async def test_normalizes_valid_features_and_skips_invalid(ndw_geojson_response) -> None:
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )

    # 5 features in fixture: 3 geldig, 1 met ongeldige coördinaten, 1 zonder id.
    assert len(result.locations) == 3
    ids = {loc.provider_location_id for loc in result.locations}
    assert ids == {"NDW-TEST-001", "NDW-TEST-002", "NDW-TEST-003-PROPERTIES-ID-FALLBACK"}
    assert result.source_name == "NDW DOT-NL"


async def test_feature_id_read_from_feature_level(ndw_geojson_response) -> None:
    """De live NDW-API plaatst 'id' op Feature-niveau, niet in properties (regressietest)."""
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )

    location = next(loc for loc in result.locations if loc.provider_location_id == "NDW-TEST-001")
    assert location is not None


async def test_feature_id_falls_back_to_properties_id(ndw_geojson_response) -> None:
    """Defensieve fallback: als 'id' toch (ook) in properties staat, moet dat ook werken."""
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )

    ids = {loc.provider_location_id for loc in result.locations}
    assert "NDW-TEST-003-PROPERTIES-ID-FALLBACK" in ids


async def test_connector_type_mapping(ndw_geojson_response) -> None:
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )
    location = next(loc for loc in result.locations if loc.provider_location_id == "NDW-TEST-001")

    assert ConnectorType.TYPE_2 in location.connector_types
    assert ConnectorType.CCS in location.connector_types
    assert location.max_power_kw == 150


async def test_availability_counts_match_aggregate(ndw_geojson_response) -> None:
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )
    location = next(loc for loc in result.locations if loc.provider_location_id == "NDW-TEST-001")

    # availabilities[]: (available=2,total=3) + (available=0,total=1) => 4 EVSE's, 2 beschikbaar
    assert location.total_evses == 4
    assert location.available_evses == 2
    assert location.realtime_data_available is True


async def test_location_without_availabilities_is_not_realtime(ndw_geojson_response) -> None:
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )
    location = next(loc for loc in result.locations if loc.provider_location_id == "NDW-TEST-002")

    assert location.total_evses == 0
    assert location.realtime_data_available is False


async def test_radius_filter_excludes_far_locations(ndw_geojson_response) -> None:
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    # NDW-TEST-001 ligt ~26m van de origin, NDW-TEST-002 ~380m: bij radius=10m
    # vallen beide af.
    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=10, max_results=10
    )
    assert result.locations == ()

    # Bij radius=100m blijft alleen NDW-TEST-001 over.
    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=100, max_results=10
    )
    assert [loc.provider_location_id for loc in result.locations] == ["NDW-TEST-001"]


async def test_min_power_filter(ndw_geojson_response) -> None:
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT,
        longitude=_ORIGIN_LON,
        radius_m=20000,
        max_results=10,
        min_power_kw=100,
    )

    assert len(result.locations) == 1
    assert result.locations[0].provider_location_id == "NDW-TEST-001"


async def test_connector_type_filter(ndw_geojson_response) -> None:
    provider = NdwProvider(FakeApiClient(payload=ndw_geojson_response))

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT,
        longitude=_ORIGIN_LON,
        radius_m=20000,
        max_results=10,
        connector_types=frozenset({ConnectorType.CHADEMO}),
    )

    assert result.locations == ()


async def test_auth_error_translated() -> None:
    provider = NdwProvider(FakeApiClient(exception=ApiAuthError("nope")))

    with pytest.raises(ProviderAuthError):
        await provider.async_get_locations(
            latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=1000, max_results=5
        )


async def test_rate_limited_error_translated() -> None:
    provider = NdwProvider(FakeApiClient(exception=ApiRateLimitedError("slow down", retry_after=5)))

    with pytest.raises(ProviderRateLimitedError) as exc_info:
        await provider.async_get_locations(
            latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=1000, max_results=5
        )
    assert exc_info.value.retry_after == 5


async def test_connection_error_translated() -> None:
    provider = NdwProvider(FakeApiClient(exception=ApiConnectionError("down")))

    with pytest.raises(ProviderConnectionError):
        await provider.async_get_locations(
            latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=1000, max_results=5
        )


# --------------------------------------------------------------------------
# TomTom
# --------------------------------------------------------------------------


async def test_tomtom_requires_api_key() -> None:
    provider = TomTomProvider(FakeApiClient(payload={"results": []}), api_key=None)

    with pytest.raises(ProviderAuthError):
        await provider.async_get_locations(
            latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=1000, max_results=5
        )


async def test_tomtom_normalizes_per_evse_status(tomtom_response) -> None:
    provider = TomTomProvider(FakeApiClient(payload=tomtom_response), api_key="test-key")

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )

    assert len(result.locations) == 1
    location = result.locations[0]
    assert location.provider_location_id == "tomtom-1"
    assert location.total_evses == 2
    assert location.available_evses == 1
    evse_statuses = {evse.status for evse in location.evses}
    assert evse_statuses == {ChargePointStatus.AVAILABLE, ChargePointStatus.OCCUPIED}
    assert ConnectorType.TYPE_2 in location.connector_types
    assert ConnectorType.CCS in location.connector_types
    assert location.source_quality is DataQuality.REALTIME
    assert result.source_name == "TomTom"


async def test_tomtom_skips_invalid_result(tomtom_response) -> None:
    provider = TomTomProvider(FakeApiClient(payload=tomtom_response), api_key="test-key")

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )

    ids = [loc.provider_location_id for loc in result.locations]
    assert "tomtom-invalid" not in ids


# --------------------------------------------------------------------------
# Open Charge Map
# --------------------------------------------------------------------------


async def test_ocm_requires_api_key() -> None:
    provider = OpenChargeMapProvider(FakeApiClient(payload=[]), api_key=None)

    with pytest.raises(ProviderAuthError):
        await provider.async_get_locations(
            latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=1000, max_results=5
        )


async def test_ocm_never_reports_realtime_availability(ocm_response) -> None:
    provider = OpenChargeMapProvider(FakeApiClient(payload=ocm_response), api_key="test-key")

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )

    assert result.realtime_available is False
    assert len(result.locations) == 1
    location = result.locations[0]
    assert location.realtime_data_available is False
    assert location.source_quality is DataQuality.STATIC
    # Nooit AVAILABLE tonen zonder echte realtime data (opdracht §10).
    assert location.available_evses == 0
    assert location.is_available is False


async def test_ocm_operational_false_maps_to_out_of_order(ocm_response) -> None:
    provider = OpenChargeMapProvider(FakeApiClient(payload=ocm_response), api_key="test-key")

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )
    location = result.locations[0]

    # Connection 1: Type 2, Quantity 2, operational -> 2x UNKNOWN.
    # Connection 2: CCS, Quantity 1, niet operationeel -> 1x OUT_OF_ORDER.
    assert location.total_evses == 3
    assert location.out_of_order_evses == 1
    assert location.unknown_evses == 2


async def test_ocm_skips_record_without_id(ocm_response) -> None:
    provider = OpenChargeMapProvider(FakeApiClient(payload=ocm_response), api_key="test-key")

    result = await provider.async_get_locations(
        latitude=_ORIGIN_LAT, longitude=_ORIGIN_LON, radius_m=20000, max_results=10
    )

    assert len(result.locations) == 1
