"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor unload/reload-lifecycle — moet idempotent en zonder resterende
state kunnen (opdracht §28/§37).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.models import ProviderFetchResult

_UNLOAD_SETTLE_ATTEMPTS = 10


async def _async_wait_until_removed(hass, entity_id: str) -> None:
    """Wacht tot een entity-state volledig verdwenen is na unload.

    Opruimen na `async_unload_platforms` loopt deels via achtergrondtaken
    waarvan het aantal/de volgorde niet gegarandeerd is (bleek uit CI:
    verschillende entities bleven per run op wisselende momenten nog even
    'unavailable' staan i.p.v. direct None). In plaats van te gokken met een
    vast aantal `async_block_till_done()`-aanroepen, pollen we kort totdat de
    state daadwerkelijk weg is.
    """
    for _ in range(_UNLOAD_SETTLE_ATTEMPTS):
        await hass.async_block_till_done(wait_background_tasks=True)
        if hass.states.get(entity_id) is None:
            return
        await asyncio.sleep(0)
    assert hass.states.get(entity_id) is None, (
        f"{entity_id} nog niet verwijderd na {_UNLOAD_SETTLE_ATTEMPTS} pogingen"
    )


def _set_zone_and_person(hass) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": 100, "friendly_name": "Woonwijk"},
    )
    hass.states.async_set("person.vincent", "home")


async def test_unload_entry_removes_entities_and_stops_coordinator(
    hass, mock_config_entry_data
) -> None:
    _set_zone_and_person(hass)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data)
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.state is ConfigEntryState.NOT_LOADED
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    # Entity registry-entries blijven bewaard (HA-conventie), maar er mogen
    # geen actieve states meer zijn na unload.
    for entity in entities:
        await _async_wait_until_removed(hass, entity.entity_id)


async def test_reload_entry_is_idempotent(hass, mock_config_entry_data) -> None:
    _set_zone_and_person(hass)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data)
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
