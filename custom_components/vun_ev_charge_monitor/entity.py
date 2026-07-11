"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Basisentiteit — regelt het gedeelde device (één per config entry) en
stabiele unique ID's (opdracht §17/§28).
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONFIGURATION_URL, DOMAIN, INTEGRATION_VERSION, MANUFACTURER, MODEL
from .coordinator import VunEvChargeMonitorCoordinator


class VunEvChargeMonitorEntity(CoordinatorEntity[VunEvChargeMonitorCoordinator]):
    """Basisklasse voor alle entities van deze integratie."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: VunEvChargeMonitorCoordinator, unique_id_suffix: str
    ) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=coordinator.config_entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=INTEGRATION_VERSION,
            configuration_url=CONFIGURATION_URL,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Blijf beschikbaar zolang er ooit geldige data is opgehaald.

        Bij een tijdelijke providerfout behoudt de coordinator de laatst
        geldige dataset (opdracht §19); entities tonen deze dan door,
        i.p.v. naar 'unavailable' te springen. De binary_sensor
        `data_stale` signaleert apart dat de data verouderd is.
        """
        return self.coordinator.data is not None
