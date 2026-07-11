"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de `get_nearby_chargers`-service (opdracht §26).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN, SERVICE_GET_NEARBY_CHARGERS
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
        evses=(Evse(evse_id="loc-1-1", status=ChargePointStatus.AVAILABLE, connectors=()),),
        realtime_data_available=True,
        provider_status_raw=None,
        last_status_update=dt_util.utcnow(),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME,
    )


async def test_get_nearby_chargers_returns_bounded_response(hass, mock_config_entry_data) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": 1500, "friendly_name": "Woonwijk"},
    )
    hass.states.async_set("person.vincent", "home")
    entry = MockConfigEntry(domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data)
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

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NEARBY_CHARGERS,
            {"config_entry_id": entry.entry_id, "max_results": 5},
            blocking=True,
            return_response=True,
        )

    assert response["locations"][0]["name"] == "P+R Centrum"
    assert response["locations"][0]["available_connectors"] == 1
    assert response["realtime_available"] is True
    # Geen ruwe providerdata of gevoelige configuratie in de response.
    assert "api_key" not in response
    assert "tracked_entities" not in response


async def test_get_nearby_chargers_rejects_unknown_entry(hass) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_NEARBY_CHARGERS,
            {"config_entry_id": "does-not-exist"},
            blocking=True,
            return_response=True,
        )
