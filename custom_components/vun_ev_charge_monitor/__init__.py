"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Setup/unload-lifecycle voor VUN EV Charge Monitor. Gebruikt
ConfigEntry.runtime_data (geen globale mutable state, opdracht §28) en
laat reload volledig over aan OptionsFlowWithReload.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiClient
from .const import (
    CONF_PROVIDER,
    CONF_SIMULATION_MODE,
    CONF_ZONE,
    DEFAULT_SIMULATION_MODE,
    DOMAIN,
    MARKERS_URL_PATH,
    NDW_BACKOFF_BASE_S,
    NDW_CONNECT_TIMEOUT_S,
    NDW_MAX_RETRIES,
    NDW_TOTAL_TIMEOUT_S,
    OCM_BACKOFF_BASE_S,
    OCM_CONNECT_TIMEOUT_S,
    OCM_MAX_RETRIES,
    OCM_TOTAL_TIMEOUT_S,
    PROVIDER_NDW,
    PROVIDER_OPEN_CHARGE_MAP,
    PROVIDER_TOMTOM,
    TOMTOM_BACKOFF_BASE_S,
    TOMTOM_CONNECT_TIMEOUT_S,
    TOMTOM_MAX_RETRIES,
    TOMTOM_TOTAL_TIMEOUT_S,
)
from .coordinator import VunEvChargeMonitorCoordinator
from .providers.base import ChargeLocationProvider
from .providers.ndw import NdwProvider
from .providers.open_charge_map import OpenChargeMapProvider
from .providers.simulation import SimulationProvider
from .providers.tomtom import TomTomProvider
from .repairs import async_clear_all_issues_for_entry
from .services import async_register_services
from .zone_tracking import ZoneEntryTracker

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.GEO_LOCATION,
]

_MARKERS_DIR = os.path.join(os.path.dirname(__file__), "markers")
_MARKERS_REGISTERED_KEY = f"{DOMAIN}_markers_static_path_registered"


async def _async_register_marker_static_path(hass: HomeAssistant) -> None:
    """Registreer de map-marker-afbeeldingen als statische bestanden (idempotent).

    Meerdere config entries (bv. meerdere zones) delen dezelfde marker-
    afbeeldingen en dus hetzelfde URL-pad — een tweede registratiepoging zou
    een aiohttp-routeconflict opleveren, vandaar deze hass.data-vlag.
    """
    if hass.data.get(_MARKERS_REGISTERED_KEY):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(MARKERS_URL_PATH, _MARKERS_DIR, cache_headers=True)]
    )
    hass.data[_MARKERS_REGISTERED_KEY] = True


@dataclass(slots=True)
class VunEvRuntimeData:
    """Runtime-only data, gekoppeld aan de config entry (niet gepersisteerd)."""

    coordinator: VunEvChargeMonitorCoordinator
    zone_tracker: ZoneEntryTracker


type VunEvConfigEntry = ConfigEntry[VunEvRuntimeData]


def _build_provider(hass: HomeAssistant, entry: VunEvConfigEntry) -> ChargeLocationProvider:
    if entry.data.get(CONF_SIMULATION_MODE, DEFAULT_SIMULATION_MODE):
        return SimulationProvider()

    session = async_get_clientsession(hass)
    provider_name = entry.data[CONF_PROVIDER]
    api_key = entry.data.get(CONF_API_KEY) or None

    if provider_name == PROVIDER_NDW:
        api_client = ApiClient(
            session,
            connect_timeout_s=NDW_CONNECT_TIMEOUT_S,
            total_timeout_s=NDW_TOTAL_TIMEOUT_S,
            max_retries=NDW_MAX_RETRIES,
            backoff_base_s=NDW_BACKOFF_BASE_S,
        )
        return NdwProvider(api_client, api_key=api_key)

    if provider_name == PROVIDER_TOMTOM:
        api_client = ApiClient(
            session,
            connect_timeout_s=TOMTOM_CONNECT_TIMEOUT_S,
            total_timeout_s=TOMTOM_TOTAL_TIMEOUT_S,
            max_retries=TOMTOM_MAX_RETRIES,
            backoff_base_s=TOMTOM_BACKOFF_BASE_S,
        )
        return TomTomProvider(api_client, api_key=api_key)

    if provider_name == PROVIDER_OPEN_CHARGE_MAP:
        api_client = ApiClient(
            session,
            connect_timeout_s=OCM_CONNECT_TIMEOUT_S,
            total_timeout_s=OCM_TOTAL_TIMEOUT_S,
            max_retries=OCM_MAX_RETRIES,
            backoff_base_s=OCM_BACKOFF_BASE_S,
        )
        return OpenChargeMapProvider(api_client, api_key=api_key)

    raise ConfigEntryNotReady(f"Provider '{provider_name}' wordt niet ondersteund")


async def async_setup_entry(hass: HomeAssistant, entry: VunEvConfigEntry) -> bool:
    """Zet een config entry op: valideer zone, bouw provider+coordinator, forward platforms."""
    zone_entity_id = entry.data[CONF_ZONE]
    if hass.states.get(zone_entity_id) is None:
        raise ConfigEntryNotReady(f"Zone {zone_entity_id} is nog niet beschikbaar")

    provider = _build_provider(hass, entry)

    coordinator = VunEvChargeMonitorCoordinator(hass, entry, provider)
    await coordinator.async_config_entry_first_refresh()

    zone_tracker = ZoneEntryTracker(hass, entry, coordinator)
    zone_tracker.async_setup()

    entry.runtime_data = VunEvRuntimeData(coordinator=coordinator, zone_tracker=zone_tracker)

    async_register_services(hass)
    await _async_register_marker_static_path(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info(
        "VUN EV Charge Monitor '%s' succesvol opgezet (provider: %s)",
        entry.title,
        entry.data[CONF_PROVIDER],
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VunEvConfigEntry) -> bool:
    """Ontlaad een config entry en ruim alle platforms, listeners en repair issues netjes op."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        if entry.runtime_data is not None:
            entry.runtime_data.zone_tracker.async_unload()
        async_clear_all_issues_for_entry(hass, entry)
    return unload_ok
