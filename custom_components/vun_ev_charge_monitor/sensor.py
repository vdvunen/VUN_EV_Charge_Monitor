"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Sensor-entiteiten (opdracht §17). Eén compacte set entry-brede sensoren —
bewust geen entity per laadpaal (voorkomt recorder-/registerbelasting).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_RATE_LIMITED,
    ERROR_UNKNOWN,
)
from .coordinator import CoordinatorData, VunEvChargeMonitorCoordinator
from .entity import VunEvChargeMonitorEntity

_API_STATUS_OK = "ok"
_API_STATUS_OPTIONS = [
    _API_STATUS_OK,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_RATE_LIMITED,
    ERROR_UNKNOWN,
]

_MAX_ATTRIBUTE_LOCATIONS = 5
_MAX_NAME_LENGTH = 60


def _top_locations_attributes(data: CoordinatorData) -> dict[str, Any]:
    """Compacte, begrensde lijst voor het sensorattribuut (opdracht §17)."""
    return {
        "top_locations": [
            {
                "name": loc.name[:_MAX_NAME_LENGTH],
                "address": (loc.address or "")[:_MAX_NAME_LENGTH] or None,
                "distance_m": round(loc.distance_m) if loc.distance_m is not None else None,
                "available": loc.available_evses,
                "total": loc.total_evses,
                "max_power_kw": loc.max_power_kw,
                "operator": (loc.operator or "")[:_MAX_NAME_LENGTH] or None,
            }
            for loc in data.locations[:_MAX_ATTRIBUTE_LOCATIONS]
        ]
    }


def _api_status(coordinator: VunEvChargeMonitorCoordinator) -> str:
    if coordinator.last_update_success:
        return _API_STATUS_OK
    return coordinator.last_error_type or ERROR_UNKNOWN


@dataclass(frozen=True, kw_only=True)
class VunEvSensorEntityDescription(SensorEntityDescription):
    """Sensorbeschrijving met een functie die de state uit CoordinatorData afleidt."""

    value_fn: Callable[[CoordinatorData], StateType]
    attributes_fn: Callable[[CoordinatorData], dict[str, Any]] | None = None


SENSOR_DESCRIPTIONS: tuple[VunEvSensorEntityDescription, ...] = (
    VunEvSensorEntityDescription(
        key="available_locations",
        translation_key="available_locations",
        icon="mdi:ev-station",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.available_location_count,
        attributes_fn=_top_locations_attributes,
    ),
    VunEvSensorEntityDescription(
        key="available_connectors",
        translation_key="available_connectors",
        icon="mdi:power-plug",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.available_connector_count,
    ),
    VunEvSensorEntityDescription(
        key="total_locations",
        translation_key="total_locations",
        icon="mdi:map-marker-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.total_location_count,
    ),
    VunEvSensorEntityDescription(
        key="total_connectors",
        translation_key="total_connectors",
        icon="mdi:power-plug-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.total_connector_count,
    ),
    VunEvSensorEntityDescription(
        key="best_location",
        translation_key="best_location",
        icon="mdi:ev-station",
        value_fn=lambda data: data.best_location.name if data.best_location else None,
    ),
    VunEvSensorEntityDescription(
        key="best_location_distance",
        translation_key="best_location_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            round(data.best_location.distance_m)
            if data.best_location and data.best_location.distance_m is not None
            else None
        ),
    ),
    VunEvSensorEntityDescription(
        key="best_location_max_power",
        translation_key="best_location_max_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.best_location.max_power_kw if data.best_location else None,
    ),
    VunEvSensorEntityDescription(
        key="best_location_operator",
        translation_key="best_location_operator",
        icon="mdi:domain",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.best_location.operator if data.best_location else None,
    ),
    VunEvSensorEntityDescription(
        key="best_location_address",
        translation_key="best_location_address",
        icon="mdi:map-marker",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.best_location.address if data.best_location else None,
    ),
    VunEvSensorEntityDescription(
        key="navigation_url",
        translation_key="navigation_url",
        icon="mdi:navigation",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.best_location.navigation_url if data.best_location else None,
    ),
    VunEvSensorEntityDescription(
        key="last_successful_update",
        translation_key="last_successful_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.fetched_at,
    ),
    VunEvSensorEntityDescription(
        key="data_source",
        translation_key="data_source",
        icon="mdi:database",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.source_name,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [
        VunEvSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(VunEvApiStatusSensor(coordinator))
    async_add_entities(entities)


class VunEvSensor(VunEvChargeMonitorEntity, SensorEntity):
    """Generieke sensor gedreven door een VunEvSensorEntityDescription."""

    entity_description: VunEvSensorEntityDescription

    def __init__(
        self,
        coordinator: VunEvChargeMonitorCoordinator,
        description: VunEvSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class VunEvApiStatusSensor(VunEvChargeMonitorEntity, SensorEntity):
    """Aparte klasse omdat de state afhangt van coordinatorstatus, niet van CoordinatorData."""

    _attr_translation_key = "api_status"
    _attr_icon = "mdi:api"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _API_STATUS_OPTIONS

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator) -> None:
        super().__init__(coordinator, "api_status")

    @property
    def native_value(self) -> StateType:
        return _api_status(self.coordinator)

    @property
    def available(self) -> bool:
        # Deze sensor toont juist de foutstatus zelf en moet dus altijd
        # zichtbaar blijven, ook wanneer de laatste update mislukte.
        return True
