"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Toont de gevonden laadlocaties als gekleurde punten op een `map`-kaart
(rood = niets beschikbaar, oranje = 1 beschikbaar, groen = 2 of meer
beschikbaar). Gebruikt HA's `geo_location`-platform — het native mechanisme
voor "toon deze externe punten op de kaart" (hetzelfde patroon als
bijvoorbeeld aardbevingen- of NL-alert-feeds).

Bewust een vast aantal "slot"-entiteiten (begrensd door `max_results`,
dezelfde limiet die overal elders al geldt) i.p.v. dynamisch entiteiten
aanmaken/verwijderen per update — veel eenvoudiger te onderhouden, en de
identiteit van "slot 1" is toch al vloeiend (het is altijd de huidige
#1-locatie, net als de `best_location`-sensor). Dit is uitdrukkelijk geen
doorbreking van opdracht §17 ("geen entity per laadpaal"): het aantal blijft
begrensd tot `max_results` (standaard 5, max. 20), niet één per gevonden
laadpaal.
"""

from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MAX_RESULTS,
    DEFAULT_MAX_RESULTS,
    DOMAIN,
    MARKER_FILE_GREEN,
    MARKER_FILE_ORANGE,
    MARKER_FILE_RED,
    MARKERS_URL_PATH,
)
from .coordinator import VunEvChargeMonitorCoordinator
from .entity import VunEvChargeMonitorEntity
from .models import ChargeLocation


def _marker_picture(available_evses: int) -> str:
    if available_evses <= 0:
        filename = MARKER_FILE_RED
    elif available_evses == 1:
        filename = MARKER_FILE_ORANGE
    else:
        filename = MARKER_FILE_GREEN
    return f"{MARKERS_URL_PATH}/{filename}"


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    max_results = entry.options.get(
        CONF_MAX_RESULTS, entry.data.get(CONF_MAX_RESULTS, DEFAULT_MAX_RESULTS)
    )
    async_add_entities(
        VunEvChargeLocationMarker(coordinator, index) for index in range(int(max_results))
    )


class VunEvChargeLocationMarker(VunEvChargeMonitorEntity, GeolocationEvent):
    """Eén kaartmarker-'slot' — toont altijd de huidige #N-laadlocatie."""

    _attr_source = DOMAIN

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator, index: int) -> None:
        super().__init__(coordinator, f"map_marker_{index}")
        self._index = index

    @property
    def _location(self) -> ChargeLocation | None:
        if self.coordinator.data is None:
            return None
        locations = self.coordinator.data.locations
        return locations[self._index] if self._index < len(locations) else None

    @property
    def available(self) -> bool:
        return self._location is not None

    @property
    def name(self) -> str:
        location = self._location
        return location.name if location else f"Marker {self._index + 1}"

    @property
    def latitude(self) -> float | None:
        location = self._location
        return location.latitude if location else None

    @property
    def longitude(self) -> float | None:
        location = self._location
        return location.longitude if location else None

    @property
    def distance(self) -> float | None:
        location = self._location
        if location is None or location.distance_m is None:
            return None
        return round(location.distance_m / 1000, 3)

    @property
    def entity_picture(self) -> str | None:
        location = self._location
        if location is None:
            return None
        return _marker_picture(location.available_evses)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        location = self._location
        if location is None:
            return None
        return {
            "available_connectors": location.available_evses,
            "total_connectors": location.total_evses,
            "operator": location.operator,
            "address": location.address,
            "navigation_url": location.navigation_url,
        }
