"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de setup-lifecycle (async_setup_entry).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.models import ProviderFetchResult


def _set_zone_and_person(hass) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": 100, "friendly_name": "Woonwijk"},
    )
    hass.states.async_set("person.vincent", "home")


async def test_setup_entry_creates_entities(hass, mock_config_entry_data) -> None:
    _set_zone_and_person(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data
    )
    entry.add_to_hass(hass)

    fake_result = ProviderFetchResult(
        locations=(),
        source_name="NDW DOT-NL",
        fetched_at=dt_util.utcnow(),
        realtime_available=False,
    )
    with patch(
        "custom_components.vun_ev_charge_monitor.providers.ndw.NdwProvider.async_get_locations",
        AsyncMock(return_value=fake_result),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    # 13 sensors + 3 binary_sensors + 2 buttons + 1 event + 5 geo_location map markers
    # (default max_results, zie DEFAULT_MAX_RESULTS in const.py).
    assert len(entities) == 24
    assert entry.runtime_data.coordinator.data is not None


async def test_setup_entry_fails_when_zone_missing(hass, mock_config_entry_data) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
