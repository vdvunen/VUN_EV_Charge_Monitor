"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor unload/reload-lifecycle — moet idempotent en zonder resterende
state kunnen (opdracht §28/§37).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.models import ProviderFetchResult


def _assert_no_stale_data(hass, entity_id: str) -> None:
    """Na unload mag een entity geen mogelijk-verouderde data meer tonen.

    De meeste entities worden volledig uit de state machine verwijderd
    (state wordt None). Sensoren met `state_class` (measurement, voor
    langetermijnstatistieken) blijven bij Home Assistant zelf bewust als
    'unavailable' geregistreerd i.p.v. volledig verdwijnen, om continuïteit
    in statistiekgrafieken te behouden — geverifieerd via CI (consistent,
    niet tijdgebonden, dus geen race maar doelbewust HA-kerngedrag). Beide
    uitkomsten zijn hier acceptabel; alleen een andere/stale waarde niet.
    """
    state = hass.states.get(entity_id)
    if state is not None:
        assert state.state == STATE_UNAVAILABLE, (
            f"{entity_id} heeft na unload een onverwachte state: {state.state!r}"
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
    # Entity registry-entries blijven bewaard (HA-conventie). States zijn na
    # unload ofwel volledig weg, ofwel 'unavailable' (statistiek-sensoren) —
    # zie _assert_no_stale_data.
    for entity in entities:
        _assert_no_stale_data(hass, entity.entity_id)


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
