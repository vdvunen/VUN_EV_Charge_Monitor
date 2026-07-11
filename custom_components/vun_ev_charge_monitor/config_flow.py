"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Config flow + options flow. Volledig via de UI configureerbaar, geen YAML
(opdracht §11). Config- en optionsflow delen dezelfde schema-opbouw en
validatielogica om dubbele logica te voorkomen (opdracht §42).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiClient
from .const import (
    CONF_CONNECTOR_TYPES,
    CONF_LANGUAGE,
    CONF_MAX_DATA_AGE,
    CONF_MAX_RESULTS,
    CONF_MIN_POWER_KW,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_NOTIFICATION_TARGET,
    CONF_NOTIFY_ON_AVAILABILITY_CHANGE,
    CONF_NOTIFY_ON_ZONE_ENTRY,
    CONF_PROVIDER,
    CONF_RADIUS,
    CONF_SIMULATION_MODE,
    CONF_TRACKED_ENTITIES,
    CONF_UPDATE_INTERVAL,
    CONF_USE_ZONE_RADIUS,
    CONF_ZONE,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_DATA_AGE_MIN,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_POWER_KW,
    DEFAULT_NOTIFICATION_COOLDOWN_MIN,
    DEFAULT_NOTIFY_ON_AVAILABILITY_CHANGE,
    DEFAULT_NOTIFY_ON_ZONE_ENTRY,
    DEFAULT_PROVIDER,
    DEFAULT_RADIUS_M,
    DEFAULT_SIMULATION_MODE,
    DEFAULT_UPDATE_INTERVAL_S,
    DEFAULT_USE_ZONE_RADIUS,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_INVALID_ENTITY,
    ERROR_INVALID_INTERVAL,
    ERROR_INVALID_NOTIFICATION_SERVICE,
    ERROR_INVALID_RADIUS,
    ERROR_INVALID_ZONE,
    ERROR_RATE_LIMITED,
    ERROR_UNKNOWN,
    ERROR_UNSUPPORTED_PROVIDER,
    LANGUAGES,
    MAX_MAX_DATA_AGE_MIN,
    MAX_MAX_RESULTS,
    MAX_NOTIFICATION_COOLDOWN_MIN,
    MAX_RADIUS_M,
    MAX_UPDATE_INTERVAL_S,
    MIN_MAX_DATA_AGE_MIN,
    MIN_MAX_RESULTS,
    MIN_NOTIFICATION_COOLDOWN_MIN,
    MIN_RADIUS_M,
    MIN_UPDATE_INTERVAL_S,
    NDW_CONNECT_TIMEOUT_S,
    NDW_TOTAL_TIMEOUT_S,
    OCM_CONNECT_TIMEOUT_S,
    OCM_TOTAL_TIMEOUT_S,
    PROVIDER_NDW,
    PROVIDER_OPEN_CHARGE_MAP,
    PROVIDER_TOMTOM,
    SUPPORTED_PROVIDERS,
    TOMTOM_CONNECT_TIMEOUT_S,
    TOMTOM_TOTAL_TIMEOUT_S,
)
from .models import ConnectorType
from .providers.base import ProviderAuthError, ProviderConnectionError, ProviderRateLimitedError
from .providers.ndw import NdwProvider
from .providers.open_charge_map import OpenChargeMapProvider
from .providers.tomtom import TomTomProvider

_LOGGER = logging.getLogger(__name__)

_TRACKED_DOMAINS = ("person", "device_tracker")


# --------------------------------------------------------------------------
# Schema-opbouw (gedeeld tussen ConfigFlow en OptionsFlow)
# --------------------------------------------------------------------------


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ZONE, default=defaults.get(CONF_ZONE)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="zone")
            ),
            vol.Required(
                CONF_PROVIDER, default=defaults.get(CONF_PROVIDER, DEFAULT_PROVIDER)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(SUPPORTED_PROVIDERS),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="provider",
                )
            ),
            vol.Optional(
                CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_SIMULATION_MODE,
                default=defaults.get(CONF_SIMULATION_MODE, DEFAULT_SIMULATION_MODE),
            ): selector.BooleanSelector(),
        }
    )


def _tracking_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_TRACKED_ENTITIES, default=defaults.get(CONF_TRACKED_ENTITIES, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=list(_TRACKED_DOMAINS), multiple=True
                )
            ),
        }
    )


def _search_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_USE_ZONE_RADIUS,
                default=defaults.get(CONF_USE_ZONE_RADIUS, DEFAULT_USE_ZONE_RADIUS),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_RADIUS, default=defaults.get(CONF_RADIUS, DEFAULT_RADIUS_M)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_RADIUS_M,
                    max=MAX_RADIUS_M,
                    step=100,
                    unit_of_measurement="m",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MAX_RESULTS,
                default=defaults.get(CONF_MAX_RESULTS, DEFAULT_MAX_RESULTS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_MAX_RESULTS,
                    max=MAX_MAX_RESULTS,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_CONNECTOR_TYPES, default=defaults.get(CONF_CONNECTOR_TYPES, [])
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        connector.value
                        for connector in ConnectorType
                        if connector is not ConnectorType.UNKNOWN
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="connector_type",
                )
            ),
            vol.Required(
                CONF_MIN_POWER_KW,
                default=defaults.get(CONF_MIN_POWER_KW, DEFAULT_MIN_POWER_KW),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=400,
                    step=1,
                    unit_of_measurement="kW",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_S),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL_S,
                    max=MAX_UPDATE_INTERVAL_S,
                    step=30,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MAX_DATA_AGE,
                default=defaults.get(CONF_MAX_DATA_AGE, DEFAULT_MAX_DATA_AGE_MIN),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_MAX_DATA_AGE_MIN,
                    max=MAX_MAX_DATA_AGE_MIN,
                    step=5,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _notifications_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFICATION_TARGET, default=defaults.get(CONF_NOTIFICATION_TARGET, {})
            ): selector.TargetSelector(),
            vol.Required(
                CONF_NOTIFY_ON_ZONE_ENTRY,
                default=defaults.get(
                    CONF_NOTIFY_ON_ZONE_ENTRY, DEFAULT_NOTIFY_ON_ZONE_ENTRY
                ),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_NOTIFY_ON_AVAILABILITY_CHANGE,
                default=defaults.get(
                    CONF_NOTIFY_ON_AVAILABILITY_CHANGE,
                    DEFAULT_NOTIFY_ON_AVAILABILITY_CHANGE,
                ),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_NOTIFICATION_COOLDOWN,
                default=defaults.get(
                    CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN_MIN
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_NOTIFICATION_COOLDOWN_MIN,
                    max=MAX_NOTIFICATION_COOLDOWN_MIN,
                    step=5,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_LANGUAGE, default=defaults.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(LANGUAGES),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="language",
                )
            ),
        }
    )


# --------------------------------------------------------------------------
# Validatie
# --------------------------------------------------------------------------


def _validate_zone(hass: HomeAssistant, zone_entity_id: str) -> tuple[float, float] | None:
    zone_state = hass.states.get(zone_entity_id)
    if zone_state is None:
        return None
    try:
        return (
            float(zone_state.attributes["latitude"]),
            float(zone_state.attributes["longitude"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _validate_tracked_entities(hass: HomeAssistant, entity_ids: list[str]) -> bool:
    if not entity_ids:
        return False
    for entity_id in entity_ids:
        if entity_id.split(".", 1)[0] not in _TRACKED_DOMAINS:
            return False
        if hass.states.get(entity_id) is None:
            return False
    return True


def _validate_notification_target(hass: HomeAssistant, target: dict[str, Any]) -> bool:
    """Lichte validatie: bestaande entity_id's in het target moeten bestaan.

    Device/area/label-targeting wordt niet dieper gevalideerd — de
    doelregistratie garandeert daar al geldigheid via de TargetSelector-UI.
    """
    entity_ids = target.get("entity_id") if target else None
    if not entity_ids:
        return True
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    return all(hass.states.get(entity_id) is not None for entity_id in entity_ids)


def _build_test_provider(hass: HomeAssistant, provider_name: str, api_key: str | None):
    """Bouw een kortstondige providerinstantie voor de config-flow-verbindingstest.

    `max_retries=0`: een config-flowvalidatie mag de gebruiker niet laten
    wachten op de volledige retry/back-off-reeks uit api.py.
    """
    session = async_get_clientsession(hass)
    if provider_name == PROVIDER_NDW:
        api_client = ApiClient(
            session,
            connect_timeout_s=NDW_CONNECT_TIMEOUT_S,
            total_timeout_s=NDW_TOTAL_TIMEOUT_S,
            max_retries=0,
        )
        return NdwProvider(api_client, api_key=api_key or None)
    if provider_name == PROVIDER_TOMTOM:
        api_client = ApiClient(
            session,
            connect_timeout_s=TOMTOM_CONNECT_TIMEOUT_S,
            total_timeout_s=TOMTOM_TOTAL_TIMEOUT_S,
            max_retries=0,
        )
        return TomTomProvider(api_client, api_key=api_key or None)
    if provider_name == PROVIDER_OPEN_CHARGE_MAP:
        api_client = ApiClient(
            session,
            connect_timeout_s=OCM_CONNECT_TIMEOUT_S,
            total_timeout_s=OCM_TOTAL_TIMEOUT_S,
            max_retries=0,
        )
        return OpenChargeMapProvider(api_client, api_key=api_key or None)
    return None


async def _async_test_provider_connection(
    hass: HomeAssistant,
    provider_name: str,
    api_key: str | None,
    latitude: float,
    longitude: float,
) -> str | None:
    """Test de providerverbinding. Retourneert een foutcode of None bij succes."""
    if provider_name not in SUPPORTED_PROVIDERS:
        return ERROR_UNSUPPORTED_PROVIDER

    provider = _build_test_provider(hass, provider_name, api_key)
    if provider is None:
        return ERROR_UNSUPPORTED_PROVIDER

    try:
        await provider.async_get_locations(
            latitude=latitude, longitude=longitude, radius_m=MIN_RADIUS_M, max_results=1
        )
    except ProviderAuthError:
        return ERROR_INVALID_AUTH
    except ProviderRateLimitedError:
        return ERROR_RATE_LIMITED
    except ProviderConnectionError:
        return ERROR_CANNOT_CONNECT
    except Exception as err:  # noqa: BLE001 - onbekende fout mag config flow niet crashen
        # Bewust geen _LOGGER.exception()/volledige traceback: sommige
        # providerexcepties (bv. aiohttp ContentTypeError) embedden de
        # volledige requeststring inclusief querystring, en TomTom stuurt
        # zijn API-key als queryparameter. Alleen het exceptietype loggen
        # voorkomt dat een key alsnog in de HA-log terechtkomt (opdracht §22).
        _LOGGER.error("Onverwachte fout tijdens providertest: %s", type(err).__name__)
        return ERROR_UNKNOWN
    return None


# --------------------------------------------------------------------------
# Config flow
# --------------------------------------------------------------------------


class VunEvChargeMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow voor VUN EV Charge Monitor."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reconfigure_entry = (
            self._get_reconfigure_entry() if self.source == SOURCE_RECONFIGURE else None
        )
        defaults = reconfigure_entry.data if reconfigure_entry else {}

        if user_input is not None:
            zone_coords = _validate_zone(self.hass, user_input[CONF_ZONE])
            if zone_coords is None:
                errors["base"] = ERROR_INVALID_ZONE
            else:
                connection_error = (
                    None
                    if user_input.get(CONF_SIMULATION_MODE)
                    else await _async_test_provider_connection(
                        self.hass,
                        user_input[CONF_PROVIDER],
                        user_input.get(CONF_API_KEY),
                        *zone_coords,
                    )
                )
                if connection_error:
                    errors["base"] = connection_error
                else:
                    self._data.update(user_input)
                    await self.async_set_unique_id(user_input[CONF_ZONE])
                    self._abort_if_unique_id_configured()
                    return await self.async_step_tracking()

        return self.async_show_form(
            step_id="user", data_schema=_user_schema(defaults), errors=errors
        )

    async def async_step_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reconfigure_entry = (
            self._get_reconfigure_entry() if self.source == SOURCE_RECONFIGURE else None
        )
        defaults = reconfigure_entry.data if reconfigure_entry else self._data

        if user_input is not None:
            if not _validate_tracked_entities(
                self.hass, user_input[CONF_TRACKED_ENTITIES]
            ):
                errors["base"] = ERROR_INVALID_ENTITY
            else:
                self._data.update(user_input)
                return await self.async_step_search()

        return self.async_show_form(
            step_id="tracking", data_schema=_tracking_schema(defaults), errors=errors
        )

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reconfigure_entry = (
            self._get_reconfigure_entry() if self.source == SOURCE_RECONFIGURE else None
        )
        defaults = reconfigure_entry.data if reconfigure_entry else self._data

        if user_input is not None:
            if not (MIN_RADIUS_M <= user_input[CONF_RADIUS] <= MAX_RADIUS_M):
                errors["base"] = ERROR_INVALID_RADIUS
            elif not (
                MIN_UPDATE_INTERVAL_S
                <= user_input[CONF_UPDATE_INTERVAL]
                <= MAX_UPDATE_INTERVAL_S
            ):
                errors["base"] = ERROR_INVALID_INTERVAL
            else:
                self._data.update(user_input)
                return await self.async_step_notifications()

        return self.async_show_form(
            step_id="search", data_schema=_search_schema(defaults), errors=errors
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reconfigure_entry = (
            self._get_reconfigure_entry() if self.source == SOURCE_RECONFIGURE else None
        )
        defaults = reconfigure_entry.data if reconfigure_entry else self._data

        if user_input is not None:
            if not _validate_notification_target(
                self.hass, user_input.get(CONF_NOTIFICATION_TARGET, {})
            ):
                errors["base"] = ERROR_INVALID_NOTIFICATION_SERVICE
            else:
                self._data.update(user_input)
                if reconfigure_entry is not None:
                    return self.async_update_reload_and_abort(
                        reconfigure_entry, data=self._data
                    )
                zone_state = self.hass.states.get(self._data[CONF_ZONE])
                title = zone_state.name if zone_state else self._data[CONF_ZONE]
                return self.async_create_entry(title=title, data=self._data)

        return self.async_show_form(
            step_id="notifications",
            data_schema=_notifications_schema(defaults),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._data = dict(self._get_reconfigure_entry().data)
        return await self.async_step_user(user_input)

    # --- Reauth --------------------------------------------------------

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            zone_coords = _validate_zone(self.hass, reauth_entry.data[CONF_ZONE])
            if zone_coords is None:
                errors["base"] = ERROR_INVALID_ZONE
            else:
                connection_error = await _async_test_provider_connection(
                    self.hass,
                    reauth_entry.data[CONF_PROVIDER],
                    user_input.get(CONF_API_KEY),
                    *zone_coords,
                )
                if connection_error:
                    errors["base"] = connection_error
                else:
                    return self.async_update_reload_and_abort(
                        reauth_entry,
                        data={**reauth_entry.data, CONF_API_KEY: user_input.get(CONF_API_KEY)},
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_API_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VunEvChargeMonitorOptionsFlow:
        return VunEvChargeMonitorOptionsFlow()


# --------------------------------------------------------------------------
# Options flow
# --------------------------------------------------------------------------


class VunEvChargeMonitorOptionsFlow(OptionsFlowWithReload):
    """Options flow — hergebruikt dezelfde stappen/validatie als de config flow."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._data = self._current()
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            zone_coords = _validate_zone(self.hass, user_input[CONF_ZONE])
            if zone_coords is None:
                errors["base"] = ERROR_INVALID_ZONE
            else:
                connection_error = (
                    None
                    if user_input.get(CONF_SIMULATION_MODE)
                    else await _async_test_provider_connection(
                        self.hass,
                        user_input[CONF_PROVIDER],
                        user_input.get(CONF_API_KEY),
                        *zone_coords,
                    )
                )
                if connection_error:
                    errors["base"] = connection_error
                else:
                    self._data.update(user_input)
                    return await self.async_step_tracking()

        return self.async_show_form(
            step_id="user", data_schema=_user_schema(self._data), errors=errors
        )

    async def async_step_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not _validate_tracked_entities(
                self.hass, user_input[CONF_TRACKED_ENTITIES]
            ):
                errors["base"] = ERROR_INVALID_ENTITY
            else:
                self._data.update(user_input)
                return await self.async_step_search()

        return self.async_show_form(
            step_id="tracking", data_schema=_tracking_schema(self._data), errors=errors
        )

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (MIN_RADIUS_M <= user_input[CONF_RADIUS] <= MAX_RADIUS_M):
                errors["base"] = ERROR_INVALID_RADIUS
            elif not (
                MIN_UPDATE_INTERVAL_S
                <= user_input[CONF_UPDATE_INTERVAL]
                <= MAX_UPDATE_INTERVAL_S
            ):
                errors["base"] = ERROR_INVALID_INTERVAL
            else:
                self._data.update(user_input)
                return await self.async_step_notifications()

        return self.async_show_form(
            step_id="search", data_schema=_search_schema(self._data), errors=errors
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not _validate_notification_target(
                self.hass, user_input.get(CONF_NOTIFICATION_TARGET, {})
            ):
                errors["base"] = ERROR_INVALID_NOTIFICATION_SERVICE
            else:
                self._data.update(user_input)
                # Zone/tracked_entities/provider blijven ook in `data` staan
                # (voor migratiebestendigheid); options bevat de volledige,
                # actuele configuratie en heeft voorrang (zie coordinator._get_config_value).
                return self.async_create_entry(data=self._data)

        return self.async_show_form(
            step_id="notifications",
            data_schema=_notifications_schema(self._data),
            errors=errors,
        )
