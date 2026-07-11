"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor zone-entrydetectie: transitiecontrole, startup-guard, debounce,
cooldown en listenercleanup (opdracht §15/§37).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN, SIGNAL_ZONE_ENTERED
from custom_components.vun_ev_charge_monitor.coordinator import VunEvChargeMonitorCoordinator
from custom_components.vun_ev_charge_monitor.models import ProviderFetchResult
from custom_components.vun_ev_charge_monitor.providers.base import ChargeLocationProvider
from custom_components.vun_ev_charge_monitor.zone_tracking import ZoneEntryTracker, _is_zone_entry


class _FakeProvider(ChargeLocationProvider):
    name = "fake"

    async def async_get_locations(self, **kwargs) -> ProviderFetchResult:
        return ProviderFetchResult(
            locations=(), source_name="Fake", fetched_at=dt_util.utcnow(), realtime_available=True
        )


def _set_zone(hass) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": 100, "friendly_name": "Woonwijk"},
    )


def _make_entry(hass, **overrides) -> MockConfigEntry:
    data = {
        "zone": "zone.woonwijk",
        "provider": "ndw",
        "api_key": "",
        "simulation_mode": False,
        "tracked_entities": ["person.vincent"],
        "use_zone_radius": False,
        "radius": 1500,
        "max_results": 5,
        "connector_types": [],
        "min_power_kw": 0.0,
        "update_interval": 300,
        "max_data_age": 30,
        "notification_target": {"entity_id": ["notify.mobile_app_test"]},
        "notify_on_zone_entry": True,
        "notify_on_availability_change": False,
        "notification_cooldown": 30,
        "language": "nl",
    }
    data.update(overrides)
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return entry


def test_is_zone_entry_valid_transition(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    old_state = hass.states.get("person.vincent")
    hass.states.async_set("person.vincent", "woonwijk")
    new_state = hass.states.get("person.vincent")

    assert _is_zone_entry(old_state, new_state, "woonwijk") is True


def test_is_zone_entry_false_when_already_in_zone(hass) -> None:
    hass.states.async_set("person.vincent", "woonwijk")
    old_state = hass.states.get("person.vincent")
    hass.states.async_set("person.vincent", "woonwijk")
    new_state = hass.states.get("person.vincent")

    assert _is_zone_entry(old_state, new_state, "woonwijk") is False


def test_is_zone_entry_false_for_unknown_old_state(hass) -> None:
    hass.states.async_set("person.vincent", STATE_UNKNOWN)
    old_state = hass.states.get("person.vincent")
    hass.states.async_set("person.vincent", "woonwijk")
    new_state = hass.states.get("person.vincent")

    assert _is_zone_entry(old_state, new_state, "woonwijk") is False


def test_is_zone_entry_false_without_old_state() -> None:
    class _FakeState:
        state = "woonwijk"

    assert _is_zone_entry(None, _FakeState(), "woonwijk") is False


async def test_zone_entry_triggers_notification(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    entry = _make_entry(hass)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, _FakeProvider())
    await coordinator.async_refresh()

    tracker = ZoneEntryTracker(hass, entry, coordinator)
    tracker._startup_complete = True
    tracker.async_setup()

    events = []
    hass.bus.async_listen(SIGNAL_ZONE_ENTERED, lambda event: events.append(event))

    with patch(
        "custom_components.vun_ev_charge_monitor.zone_tracking.async_send_charge_notification",
        AsyncMock(),
    ) as mock_notify:
        hass.states.async_set("person.vincent", "woonwijk")
        await hass.async_block_till_done()

    mock_notify.assert_called_once()
    assert len(events) == 1
    assert events[0].data["entity_id"] == "person.vincent"

    tracker.async_unload()


async def test_zone_entry_ignored_before_startup(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    entry = _make_entry(hass)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, _FakeProvider())
    await coordinator.async_refresh()

    tracker = ZoneEntryTracker(hass, entry, coordinator)
    tracker._startup_complete = False
    tracker.async_setup()

    with patch(
        "custom_components.vun_ev_charge_monitor.zone_tracking.async_send_charge_notification",
        AsyncMock(),
    ) as mock_notify:
        hass.states.async_set("person.vincent", "woonwijk")
        await hass.async_block_till_done()

    mock_notify.assert_not_called()
    tracker.async_unload()


async def test_debounce_prevents_duplicate_detection(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    hass.states.async_set("device_tracker.vincent_phone", "not_home")
    entry = _make_entry(hass, tracked_entities=["person.vincent", "device_tracker.vincent_phone"])
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, _FakeProvider())
    await coordinator.async_refresh()

    tracker = ZoneEntryTracker(hass, entry, coordinator)
    tracker._startup_complete = True
    tracker.async_setup()

    with patch(
        "custom_components.vun_ev_charge_monitor.zone_tracking.async_send_charge_notification",
        AsyncMock(),
    ) as mock_notify:
        hass.states.async_set("person.vincent", "woonwijk")
        hass.states.async_set("device_tracker.vincent_phone", "woonwijk")
        await hass.async_block_till_done()

    # Beide entiteiten komen (vrijwel) gelijktijdig de zone binnen — debounce
    # moet de tweede detectie onderdrukken.
    mock_notify.assert_called_once()
    tracker.async_unload()


async def test_cooldown_prevents_repeated_notification(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    entry = _make_entry(hass, notification_cooldown=30)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, _FakeProvider())
    await coordinator.async_refresh()

    tracker = ZoneEntryTracker(hass, entry, coordinator)
    tracker._startup_complete = True
    tracker._last_notification_sent_at = dt_util.utcnow() - timedelta(minutes=5)
    tracker.async_setup()

    with patch(
        "custom_components.vun_ev_charge_monitor.zone_tracking.async_send_charge_notification",
        AsyncMock(),
    ) as mock_notify:
        hass.states.async_set("person.vincent", "woonwijk")
        await hass.async_block_till_done()

    # Cooldown is 30 min, laatste melding was 5 min geleden -> overgeslagen.
    mock_notify.assert_not_called()
    tracker.async_unload()


async def test_notify_disabled_still_fires_event_but_no_notification(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    entry = _make_entry(hass, notify_on_zone_entry=False)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, _FakeProvider())
    await coordinator.async_refresh()

    tracker = ZoneEntryTracker(hass, entry, coordinator)
    tracker._startup_complete = True
    tracker.async_setup()

    events = []
    hass.bus.async_listen(SIGNAL_ZONE_ENTERED, lambda event: events.append(event))

    with patch(
        "custom_components.vun_ev_charge_monitor.zone_tracking.async_send_charge_notification",
        AsyncMock(),
    ) as mock_notify:
        hass.states.async_set("person.vincent", "woonwijk")
        await hass.async_block_till_done()

    mock_notify.assert_not_called()
    assert len(events) == 1
    tracker.async_unload()


async def test_unavailable_state_never_triggers_entry(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    entry = _make_entry(hass)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, _FakeProvider())
    await coordinator.async_refresh()

    tracker = ZoneEntryTracker(hass, entry, coordinator)
    tracker._startup_complete = True
    tracker.async_setup()

    with patch(
        "custom_components.vun_ev_charge_monitor.zone_tracking.async_send_charge_notification",
        AsyncMock(),
    ) as mock_notify:
        hass.states.async_set("person.vincent", STATE_UNAVAILABLE)
        await hass.async_block_till_done()

    mock_notify.assert_not_called()
    tracker.async_unload()


def test_async_unload_removes_listeners(hass) -> None:
    _set_zone(hass)
    hass.states.async_set("person.vincent", "not_home")
    entry = _make_entry(hass)
    coordinator = VunEvChargeMonitorCoordinator(hass, entry, _FakeProvider())

    tracker = ZoneEntryTracker(hass, entry, coordinator)
    tracker._startup_complete = True
    tracker.async_setup()
    assert tracker._unsub_state is not None

    tracker.async_unload()
    assert tracker._unsub_state is None

    # Idempotent: tweede unload mag niet crashen.
    tracker.async_unload()
