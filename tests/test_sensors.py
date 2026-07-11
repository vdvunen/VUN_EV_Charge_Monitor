"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de sensor-entiteiten met echte (via de coordinator gevulde)
CoordinatorData.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.models import (
    ChargeLocation,
    ChargePointStatus,
    DataQuality,
    Evse,
    ProviderFetchResult,
)


def _location() -> ChargeLocation:
    return ChargeLocation(
        provider="ndw",
        provider_location_id="loc-1",
        external_id=None,
        name="P+R Centrum",
        latitude=52.371,
        longitude=4.896,
        address="Teststraat 1",
        postal_code=None,
        city="Amsterdam",
        country="NL",
        operator="Test Operator",
        distance_m=280.0,
        navigation_url="https://example.invalid/nav",
        evses=(
            Evse(evse_id="loc-1-1", status=ChargePointStatus.AVAILABLE, connectors=()),
            Evse(evse_id="loc-1-2", status=ChargePointStatus.OCCUPIED, connectors=()),
        ),
        realtime_data_available=True,
        provider_status_raw=None,
        last_status_update=dt_util.utcnow(),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME,
    )


async def test_sensors_reflect_coordinator_data(hass, mock_config_entry_data) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": 1500, "friendly_name": "Woonwijk"},
    )
    hass.states.async_set("person.vincent", "home")

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data
    )
    entry.add_to_hass(hass)

    fake_result = ProviderFetchResult(
        locations=(_location(),),
        source_name="NDW DOT-NL",
        fetched_at=dt_util.utcnow(),
        realtime_available=True,
    )
    with patch(
        "custom_components.vun_ev_charge_monitor.providers.ndw.NdwProvider.async_get_locations",
        AsyncMock(return_value=fake_result),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    available_locations = _find_entity_state(hass, entry, "available_locations")
    assert available_locations is not None
    assert available_locations.state == "1"

    best_location = _find_entity_state(hass, entry, "best_location")
    assert best_location.state == "P+R Centrum"

    api_available = _find_entity_state(hass, entry, "api_available", platform="binary_sensor")
    assert api_available.state == "on"


def _find_entity_state(hass, entry, key_suffix: str, platform: str = "sensor"):
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.entity_id.startswith(f"{platform}.") and entity.unique_id.endswith(
            f"_{key_suffix}"
        ):
            return hass.states.get(entity.entity_id)
    return None
