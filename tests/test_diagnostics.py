"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor diagnostics-redactie — API-keys, zone, gevolgde entiteiten en
notificatiedoel mogen nooit onverhuld in de diagnostics-export verschijnen.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.components.diagnostics import REDACTED
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.diagnostics import async_get_config_entry_diagnostics
from custom_components.vun_ev_charge_monitor.models import ProviderFetchResult


async def test_diagnostics_redacts_sensitive_fields(hass, mock_config_entry_data) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": 100, "friendly_name": "Woonwijk"},
    )
    hass.states.async_set("person.vincent", "home")

    data = {
        **mock_config_entry_data,
        "api_key": "super-secret-key",
        "notification_target": {"entity_id": ["notify.mobile_app_vincent"]},
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id="zone.woonwijk", data=data)
    entry.add_to_hass(hass)

    fake_result = ProviderFetchResult(
        locations=(), source_name="NDW DOT-NL", fetched_at=dt_util.utcnow(), realtime_available=False
    )
    with patch(
        "custom_components.vun_ev_charge_monitor.providers.ndw.NdwProvider.async_get_locations",
        AsyncMock(return_value=fake_result),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    entry_data = diagnostics["config_entry_data"]
    assert entry_data["api_key"] == REDACTED
    assert entry_data["zone"] == REDACTED
    assert entry_data["tracked_entities"] == REDACTED
    assert entry_data["notification_target"] == REDACTED
    # Niet-gevoelige velden blijven gewoon zichtbaar.
    assert entry_data["radius"] == 1500
    assert diagnostics["provider"] == "ndw"
