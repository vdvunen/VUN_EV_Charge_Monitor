"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Binary sensors (opdracht §17): laadlocatie beschikbaar, API beschikbaar,
data verouderd.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VunEvChargeMonitorCoordinator
from .entity import VunEvChargeMonitorEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            VunEvChargeLocationAvailableBinarySensor(coordinator),
            VunEvApiAvailableBinarySensor(coordinator),
            VunEvDataStaleBinarySensor(coordinator),
        ]
    )


class VunEvChargeLocationAvailableBinarySensor(VunEvChargeMonitorEntity, BinarySensorEntity):
    """Aan wanneer minimaal één laadlocatie binnen de radius beschikbaar is."""

    _attr_translation_key = "charge_location_available"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator) -> None:
        super().__init__(coordinator, "charge_location_available")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.available_location_count > 0


class VunEvApiAvailableBinarySensor(VunEvChargeMonitorEntity, BinarySensorEntity):
    """Aan wanneer de laatste providercall succesvol was."""

    _attr_translation_key = "api_available"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator) -> None:
        super().__init__(coordinator, "api_available")

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def available(self) -> bool:
        # Moet juist tijdens providerfouten zichtbaar blijven.
        return True


class VunEvDataStaleBinarySensor(VunEvChargeMonitorEntity, BinarySensorEntity):
    """Aan wanneer de laatst opgehaalde data ouder is dan de ingestelde maximumleeftijd."""

    _attr_translation_key = "data_stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator) -> None:
        super().__init__(coordinator, "data_stale")

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_stale

    @property
    def available(self) -> bool:
        return True
