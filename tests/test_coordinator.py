"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de DataUpdateCoordinator: filtering, sortering, foutafhandeling,
stale-detectie en repair-issues voor verwijderde entiteiten.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.coordinator import VunEvChargeMonitorCoordinator
from custom_components.vun_ev_charge_monitor.models import (
    ChargeLocation,
    ChargePointStatus,
    DataQuality,
    Evse,
    ProviderFetchResult,
)
from custom_components.vun_ev_charge_monitor.providers.base import (
    ChargeLocationProvider,
    ProviderAuthError,
)


def _location(
    location_id: str,
    *,
    distance_m: float,
    available: bool,
    power_kw: float = 22.0,
    operator: str = "Operator",
) -> ChargeLocation:
    status = ChargePointStatus.AVAILABLE if available else ChargePointStatus.OCCUPIED
    return ChargeLocation(
        provider="ndw",
        provider_location_id=location_id,
        external_id=None,
        name=location_id,
        latitude=52.37,
        longitude=4.89,
        address=None,
        postal_code=None,
        city=None,
        country="NL",
        operator=operator,
        distance_m=distance_m,
        navigation_url="https://example.invalid",
        evses=(Evse(evse_id=f"{location_id}-1", status=status, connectors=()),),
        realtime_data_available=True,
        provider_status_raw=None,
        last_status_update=dt_util.utcnow(),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME,
    )


class FakeProvider(ChargeLocationProvider):
    name = "fake"

    def __init__(self, locations=(), exception: Exception | None = None) -> None:
        self._locations = locations
        self._exception = exception

    async def async_get_locations(self, **kwargs) -> ProviderFetchResult:
        if self._exception:
            raise self._exception
        return ProviderFetchResult(
            locations=tuple(self._locations),
            source_name="Fake",
            fetched_at=dt_util.utcnow(),
            realtime_available=True,
        )


def _make_entry(hass, **data_overrides) -> MockConfigEntry:
    data = {
        "zone": "zone.woonwijk",
        "provider": "ndw",
        "api_key": "",
        "tracked_entities": ["person.vincent"],
        "use_zone_radius": False,
        "radius": 1500,
        "max_results": 2,
        "connector_types": [],
        "min_power_kw": 0.0,
        "update_interval": 300,
        "max_data_age": 30,
        "notification_target": {},
        "notify_on_zone_entry": True,
        "notify_on_availability_change": False,
        "notification_cooldown": 30,
        "language": "nl",
    }
    data.update(data_overrides)
    entry = MockConfigEntry(domain=DOMAIN, data=data, options={})
    entry.add_to_hass(hass)
    return entry


def _set_zone(hass, radius: float = 100.0) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": radius, "friendly_name": "Woonwijk"},
    )


async def test_successful_update_sorts_available_first_then_distance(hass) -> None:
    _set_zone(hass)
    entry = _make_entry(hass)
    provider = FakeProvider(
        locations=[
            _location("far-available", distance_m=1000, available=True),
            _location("near-unavailable", distance_m=100, available=False),
            _location("near-available", distance_m=200, available=True),
        ]
    )
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, provider)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    ids = [loc.provider_location_id for loc in coordinator.data.locations]
    # max_results=2, dus 'near-unavailable' valt af ondanks kleinste afstand.
    assert ids == ["near-available", "far-available"]


async def test_zone_missing_raises_update_failed(hass) -> None:
    entry = _make_entry(hass)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, FakeProvider(locations=[]))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_provider_auth_error_raises_config_entry_auth_failed(hass) -> None:
    _set_zone(hass)
    entry = _make_entry(hass)
    coordinator = VunEvChargeMonitorCoordinator(
        hass, entry, FakeProvider(exception=ProviderAuthError("invalid key"))
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 1


async def test_stale_detection(hass) -> None:
    _set_zone(hass)
    entry = _make_entry(hass, max_data_age=5)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, FakeProvider(locations=[]))
    await coordinator.async_refresh()

    assert coordinator.is_stale is False

    # Simuleer verstreken tijd door fetched_at ver in het verleden te zetten.
    coordinator.data.fetched_at = dt_util.utcnow() - timedelta(minutes=10)
    assert coordinator.is_stale is True


async def test_operator_exclude_filters_locations(hass) -> None:
    _set_zone(hass)
    entry = _make_entry(hass, operator_exclude=["Bad Operator"])
    loc_good = _location("good", distance_m=100, available=True)
    loc_bad = _location("bad", distance_m=50, available=True, operator="Bad Operator")
    provider = FakeProvider(locations=[loc_good, loc_bad])
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, provider)

    await coordinator.async_refresh()

    ids = [loc.provider_location_id for loc in coordinator.data.locations]
    assert ids == ["good"]


async def test_driving_distance_disabled_by_default_skips_enrichment(hass) -> None:
    _set_zone(hass)
    entry = _make_entry(hass)
    provider = FakeProvider(locations=[_location("a", distance_m=100, available=True)])
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, provider)

    with patch(
        "custom_components.vun_ev_charge_monitor.coordinator.async_enrich_with_driving_distance",
        AsyncMock(),
    ) as mock_enrich:
        await coordinator.async_refresh()

    mock_enrich.assert_not_called()


async def test_driving_distance_enabled_calls_enrichment_with_top_candidates(hass) -> None:
    _set_zone(hass)
    entry = _make_entry(
        hass, use_driving_distance=True, ors_api_key="test-key", max_results=2
    )
    locations = [
        _location("a", distance_m=100, available=True),
        _location("b", distance_m=200, available=True),
        _location("c", distance_m=300, available=True),
    ]
    provider = FakeProvider(locations=locations)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, provider)

    enriched_return = tuple(sorted(locations, key=lambda loc: loc.distance_m))[:2]
    with patch(
        "custom_components.vun_ev_charge_monitor.coordinator.async_enrich_with_driving_distance",
        AsyncMock(return_value=enriched_return),
    ) as mock_enrich:
        await coordinator.async_refresh()

    mock_enrich.assert_called_once()
    _, kwargs = mock_enrich.call_args
    # max_results=2 -> slechts de top 2 kandidaten worden ter verrijking aangeboden.
    assert len(kwargs["locations"]) == 2


async def test_tracked_entity_removed_creates_and_clears_repair_issue(hass) -> None:
    _set_zone(hass)
    entry = _make_entry(hass, tracked_entities=["person.ghost"])
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, FakeProvider(locations=[]))

    await coordinator.async_refresh()
    issue_id = f"{entry.entry_id}_tracked_entity_removed_person.ghost"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    hass.states.async_set("person.ghost", "home")
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
