"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Services (opdracht §26). Alleen `get_nearby_chargers` — biedt aantoonbare
meerwaarde voor scripts/automations die de actuele topresultaten
programmatisch nodig hebben. `send_test_notification` is bewust géén
service (de button-entiteit dekt dit al, zie button.py).

Geeft nooit ruwe providerdata of gevoelige configuratie terug — alleen de
al genormaliseerde, begrensde velden die ook in de sensor-attributen staan.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import selector

from .const import DOMAIN, SERVICE_GET_NEARBY_CHARGERS, SERVICE_MAX_RESULTS

_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            selector.ConfigEntrySelectorConfig(integration=DOMAIN)
        ),
        vol.Optional("max_results", default=5): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=SERVICE_MAX_RESULTS)
        ),
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Registreer de integratieservices (idempotent, eenmalig nodig)."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_NEARBY_CHARGERS):
        return

    async def _async_get_nearby_chargers(call: ServiceCall) -> ServiceResponse:
        entry_id = call.data["config_entry_id"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise ServiceValidationError(
                f"Config entry {entry_id} bestaat niet of is niet geladen"
            )

        coordinator = entry.runtime_data.coordinator
        max_results = call.data["max_results"]
        data = coordinator.data
        locations = data.locations[:max_results] if data else ()

        return {
            "locations": [
                {
                    "name": location.name,
                    "distance_m": (
                        round(location.distance_m)
                        if location.distance_m is not None
                        else None
                    ),
                    "is_available": location.is_available,
                    "available_connectors": location.available_evses,
                    "total_connectors": location.total_evses,
                    "max_power_kw": location.max_power_kw,
                    "operator": location.operator,
                    "navigation_url": location.navigation_url,
                }
                for location in locations
            ],
            "updated_at": data.fetched_at.isoformat() if data else None,
            "realtime_available": data.realtime_available if data else None,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_NEARBY_CHARGERS,
        _async_get_nearby_chargers,
        schema=_SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
