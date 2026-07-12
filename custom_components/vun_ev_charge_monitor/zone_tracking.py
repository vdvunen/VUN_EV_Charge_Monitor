"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Zone-entrydetectie voor gevolgde person-/device_tracker-entiteiten
(opdracht §15). Luistert async naar statuswijzigingen — geen polling.

Beschermingen tegen valse/dubbele meldingen:
- startup-guard: genegeerd totdat Home Assistant volledig is opgestart,
  zodat herstelde states bij een herstart geen melding triggeren;
- transitiecontrole: alleen een overgang van "niet in zone" naar "wel in
  zone" telt, nooit een herhaling van dezelfde state;
- unknown/unavailable: nooit als geldige transitie behandeld;
- debounce: een tweede detectie binnen ZONE_ENTRY_DEBOUNCE na de vorige
  wordt genegeerd (vangt bv. een gekoppelde person + device_tracker die
  vrijwel gelijktijdig dezelfde overgang melden);
- cooldown: los van debounce — voorkomt herhaalde meldingen wanneer iemand
  kort na elkaar de zone verlaat en weer binnenkomt.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    CONF_LANGUAGE,
    CONF_MAX_RESULTS,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_NOTIFY_ON_ZONE_ENTRY,
    CONF_TRACKED_ENTITIES,
    CONF_ZONE,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_RESULTS,
    DEFAULT_NOTIFICATION_COOLDOWN_MIN,
    DEFAULT_NOTIFY_ON_ZONE_ENTRY,
    SIGNAL_ZONE_ENTERED,
    ZONE_ENTRY_DEBOUNCE,
)
from .coordinator import VunEvChargeMonitorCoordinator
from .notifications import async_send_charge_notification

_LOGGER = logging.getLogger(__name__)


def _get_config_value(entry: ConfigEntry, key: str, default):
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


class ZoneEntryTracker:
    """Bewaakt zone-entry voor de gevolgde entiteiten van één config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: VunEvChargeMonitorCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._unsub_state: Callable[[], None] | None = None
        self._unsub_started: Callable[[], None] | None = None
        self._startup_complete = hass.is_running
        self._last_entry_detected_at: datetime | None = None
        self._last_notification_sent_at: datetime | None = None

    @callback
    def async_setup(self) -> None:
        """Registreer de state-listener. Idempotent-veilig: overschrijft eerdere unsub niet."""
        tracked_entities: list[str] = self.entry.data.get(CONF_TRACKED_ENTITIES, [])
        if not tracked_entities:
            return

        self._unsub_state = async_track_state_change_event(
            self.hass, tracked_entities, self._handle_state_change
        )

        if not self._startup_complete:
            self._unsub_started = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._handle_started
            )

    @callback
    def async_unload(self) -> None:
        """Ruim listeners netjes op (opdracht §15/§28)."""
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_started is not None:
            self._unsub_started()
            self._unsub_started = None

    @callback
    def _handle_started(self, event: Event) -> None:
        self._startup_complete = True

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        if not self._startup_complete:
            _LOGGER.debug("Zone-entry genegeerd: Home Assistant is nog aan het opstarten")
            return

        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return

        zone_entity_id = self.entry.data[CONF_ZONE]
        zone_state = self.hass.states.get(zone_entity_id)
        if zone_state is None:
            return
        zone_slug = zone_entity_id.split(".", 1)[1]

        if not _is_zone_entry(old_state, new_state, zone_slug):
            return

        now = dt_util.utcnow()
        if (
            self._last_entry_detected_at is not None
            and now - self._last_entry_detected_at < ZONE_ENTRY_DEBOUNCE
        ):
            _LOGGER.debug(
                "Zone-entry van %s genegeerd (debounce actief)", new_state.entity_id
            )
            return
        self._last_entry_detected_at = now

        _LOGGER.debug(
            "Zone-entry gedetecteerd: %s is zone %s binnengekomen",
            new_state.entity_id,
            zone_slug,
        )
        self.entry.async_create_task(
            self.hass,
            self._async_handle_zone_entry(new_state.entity_id),
            "vun_ev_charge_monitor_zone_entry",
        )

    async def _async_handle_zone_entry(self, entity_id: str) -> None:
        self.hass.bus.async_fire(
            SIGNAL_ZONE_ENTERED,
            {"entry_id": self.entry.entry_id, "entity_id": entity_id},
        )

        if not _get_config_value(
            self.entry, CONF_NOTIFY_ON_ZONE_ENTRY, DEFAULT_NOTIFY_ON_ZONE_ENTRY
        ):
            return

        now = dt_util.utcnow()
        cooldown_minutes = _get_config_value(
            self.entry, CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN_MIN
        )
        if self._last_notification_sent_at is not None and cooldown_minutes > 0:
            elapsed = now - self._last_notification_sent_at
            if elapsed.total_seconds() < cooldown_minutes * 60:
                _LOGGER.debug("Melding overgeslagen: cooldown actief (%s min)", cooldown_minutes)
                return

        await self.coordinator.async_request_refresh()
        await async_send_charge_notification(
            self.hass,
            self.entry,
            self.coordinator.data,
            language=_get_config_value(self.entry, CONF_LANGUAGE, DEFAULT_LANGUAGE),
            max_results=_get_config_value(self.entry, CONF_MAX_RESULTS, DEFAULT_MAX_RESULTS),
        )
        self._last_notification_sent_at = now


def _is_zone_entry(old_state, new_state, zone_slug: str) -> bool:
    """Een geldige zone-entry: overgang van 'niet-zone' naar exact deze zone."""
    if new_state.state != zone_slug:
        return False
    if old_state is None:
        # Geen bekende vorige state (bv. eerste keer gezien na herstart) —
        # kan geen betrouwbare overgang vaststellen, dus geen melding.
        return False
    if old_state.state == zone_slug:
        return False
    return old_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
