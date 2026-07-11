"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Event-entiteit (opdracht §17) — voorkeur boven kale bus-events voor
discoverability (zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §3).

`zone_entered` wordt gevuurd via een intern bus-signaal (SIGNAL_ZONE_ENTERED)
dat `zone_tracking.py` afvuurt zodra een gevolgde person/device_tracker de
zone binnenkomt — dit ontkoppelt de detectielogica van de entity-representatie.
`availability_changed`, `charger_available` en `provider_unavailable` worden
rechtstreeks vanuit de coordinatorstatus gevuld.
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    EVENT_TYPE_AVAILABILITY_CHANGED,
    EVENT_TYPE_CHARGER_AVAILABLE,
    EVENT_TYPE_PROVIDER_UNAVAILABLE,
    EVENT_TYPE_ZONE_ENTERED,
    EVENT_TYPES,
    SIGNAL_ZONE_ENTERED,
    UPDATE_FAILURE_STREAK_FOR_REPAIR,
)
from .coordinator import VunEvChargeMonitorCoordinator
from .entity import VunEvChargeMonitorEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([VunEvActivityEventEntity(coordinator)])


class VunEvActivityEventEntity(VunEvChargeMonitorEntity, EventEntity):
    """Signaleert relevante statuswijzigingen als losse, tijdgestempelde events."""

    _attr_translation_key = "activity"
    _attr_icon = "mdi:ev-station"
    _attr_event_types = list(EVENT_TYPES)

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator) -> None:
        super().__init__(coordinator, "activity")
        self._previous_available_count: int | None = None
        self._previous_update_success: bool | None = None

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(SIGNAL_ZONE_ENTERED, self._handle_zone_entered)
        )

    @callback
    def _handle_zone_entered(self, event: Event) -> None:
        if event.data.get("entry_id") != self.coordinator.config_entry.entry_id:
            return
        self._trigger_event(
            EVENT_TYPE_ZONE_ENTERED, {"entity_id": event.data.get("entity_id")}
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._evaluate_provider_availability()
        self._evaluate_charge_availability()
        super()._handle_coordinator_update()

    def _evaluate_provider_availability(self) -> None:
        success = self.coordinator.last_update_success
        if (
            self._previous_update_success is True
            and success is False
            and self.coordinator.consecutive_failures >= UPDATE_FAILURE_STREAK_FOR_REPAIR
        ):
            self._trigger_event(
                EVENT_TYPE_PROVIDER_UNAVAILABLE,
                {"error": self.coordinator.last_error_type},
            )
        self._previous_update_success = success

    def _evaluate_charge_availability(self) -> None:
        if self.coordinator.data is None:
            return
        current = self.coordinator.data.available_connector_count
        previous = self._previous_available_count
        if previous is not None and current != previous:
            self._trigger_event(
                EVENT_TYPE_AVAILABILITY_CHANGED,
                {"available_connectors": current, "previous_available_connectors": previous},
            )
            if previous == 0 and current > 0:
                self._trigger_event(
                    EVENT_TYPE_CHARGER_AVAILABLE,
                    {"available_connectors": current},
                )
        self._previous_available_count = current
