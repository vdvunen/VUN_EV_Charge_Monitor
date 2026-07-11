"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Diagnostics (opdracht §24) — nooit ruwe locatiedata, coördinaten,
persoonsgegevens of secrets lekken; alleen geaggregeerde statusinformatie.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY

from .const import (
    CONF_MAX_DATA_AGE,
    CONF_NOTIFICATION_TARGET,
    CONF_PROVIDER,
    CONF_RADIUS,
    CONF_SIMULATION_MODE,
    CONF_TRACKED_ENTITIES,
    CONF_UPDATE_INTERVAL,
    CONF_USE_ZONE_RADIUS,
    CONF_ZONE,
    DEFAULT_SIMULATION_MODE,
    INTEGRATION_VERSION,
)

TO_REDACT: set[str] = {
    CONF_API_KEY,
    CONF_ZONE,
    CONF_TRACKED_ENTITIES,
    CONF_NOTIFICATION_TARGET,
}


async def async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data

    diagnostics: dict[str, Any] = {
        "integration_version": INTEGRATION_VERSION,
        "config_entry_version": entry.version,
        "config_entry_minor_version": entry.minor_version,
        "provider": entry.data.get(CONF_PROVIDER),
        "provider_status": "ok"
        if coordinator.last_update_success
        else (coordinator.last_error_type or "unknown"),
        "radius_m": entry.options.get(CONF_RADIUS, entry.data.get(CONF_RADIUS)),
        "use_zone_radius": entry.options.get(
            CONF_USE_ZONE_RADIUS, entry.data.get(CONF_USE_ZONE_RADIUS)
        ),
        "update_interval_s": entry.options.get(
            CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL)
        ),
        "max_data_age_min": entry.options.get(
            CONF_MAX_DATA_AGE, entry.data.get(CONF_MAX_DATA_AGE)
        ),
        "total_locations_found": data.total_location_count if data else None,
        "available_locations": data.available_location_count if data else None,
        "available_connectors": data.available_connector_count if data else None,
        "realtime_available": data.realtime_available if data else None,
        "last_successful_update": data.fetched_at.isoformat() if data else None,
        "last_update_attempt": coordinator.last_attempt.isoformat()
        if coordinator.last_attempt
        else None,
        "last_error_type": coordinator.last_error_type,
        "consecutive_failures": coordinator.consecutive_failures,
        "is_stale": coordinator.is_stale,
        "simulation_mode": entry.options.get(
            CONF_SIMULATION_MODE, entry.data.get(CONF_SIMULATION_MODE, DEFAULT_SIMULATION_MODE)
        ),
        "config_entry_data": dict(entry.data),
        "config_entry_options": dict(entry.options),
    }
    return async_redact_data(diagnostics, TO_REDACT)
