"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Centrale DataUpdateCoordinator — verzorgt providercommunicatie, filtering,
sortering, stale-datadetectie en foutafhandeling voor één config entry.
Alle entities lezen uitsluitend deze gedeelde dataset (opdracht §18).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONNECTOR_TYPES,
    CONF_MAX_DATA_AGE,
    CONF_MAX_RESULTS,
    CONF_MIN_POWER_KW,
    CONF_NOTIFICATION_TARGET,
    CONF_NOTIFY_ON_AVAILABILITY_CHANGE,
    CONF_NOTIFY_ON_ZONE_ENTRY,
    CONF_RADIUS,
    CONF_TRACKED_ENTITIES,
    CONF_UPDATE_INTERVAL,
    CONF_USE_ZONE_RADIUS,
    CONF_ZONE,
    DEFAULT_MAX_DATA_AGE_MIN,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_POWER_KW,
    DEFAULT_RADIUS_M,
    DEFAULT_UPDATE_INTERVAL_S,
    DEFAULT_USE_ZONE_RADIUS,
    DOMAIN,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_RATE_LIMITED,
    ERROR_UNKNOWN,
    UPDATE_FAILURE_STREAK_FOR_REPAIR,
)
from .models import ChargeLocation, ConnectorType
from .providers.base import (
    ChargeLocationProvider,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitedError,
    ProviderResponseError,
)
from .repairs import (
    async_clear_notification_service_missing_issue,
    async_clear_provider_unavailable_issue,
    async_clear_tracked_entity_removed_issue,
    async_clear_zone_removed_issue,
    async_create_notification_service_missing_issue,
    async_create_provider_unavailable_issue,
    async_create_tracked_entity_removed_issue,
    async_create_zone_removed_issue,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CoordinatorData:
    """Gefilterde, gesorteerde en begrensde dataset — direct bruikbaar door entities."""

    locations: tuple[ChargeLocation, ...]
    fetched_at: datetime
    source_name: str
    realtime_available: bool
    radius_m: float

    @property
    def total_location_count(self) -> int:
        return len(self.locations)

    @property
    def available_locations(self) -> tuple[ChargeLocation, ...]:
        return tuple(loc for loc in self.locations if loc.is_available)

    @property
    def available_location_count(self) -> int:
        return len(self.available_locations)

    @property
    def available_connector_count(self) -> int:
        """Som van beschikbare EVSE's over alle locaties (zie models.ChargeLocation)."""
        return sum(loc.available_evses for loc in self.locations)

    @property
    def total_connector_count(self) -> int:
        """Som van totaal aantal EVSE's over alle locaties (telbare eenheid, zie models.py)."""
        return sum(loc.total_evses for loc in self.locations)

    @property
    def best_location(self) -> ChargeLocation | None:
        return self.locations[0] if self.locations else None

    def is_stale(self, max_age: timedelta) -> bool:
        return dt_util.utcnow() - self.fetched_at > max_age


def _sort_key(location: ChargeLocation) -> tuple:
    """Standaardsortering (opdracht §14): beschikbaar eerst, dichtstbij, hoogste vermogen, meest actueel."""
    last_update_ts = (
        location.last_status_update.timestamp() if location.last_status_update else 0
    )
    return (
        not location.is_available,
        location.distance_m if location.distance_m is not None else float("inf"),
        -(location.max_power_kw or 0.0),
        -last_update_ts,
    )


class VunEvChargeMonitorCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Coordinator voor één VUN EV Charge Monitor config entry."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        provider: ChargeLocationProvider,
    ) -> None:
        update_interval_s = _get_config_value(
            config_entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_S
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_s),
        )
        self.provider = provider
        self.consecutive_failures = 0
        self.last_error_type: str | None = None
        self.last_attempt: datetime | None = None

    @property
    def max_data_age(self) -> timedelta:
        minutes = _get_config_value(
            self.config_entry, CONF_MAX_DATA_AGE, DEFAULT_MAX_DATA_AGE_MIN
        )
        return timedelta(minutes=minutes)

    @property
    def is_stale(self) -> bool:
        if self.data is None:
            return False
        return self.data.is_stale(self.max_data_age)

    async def _async_update_data(self) -> CoordinatorData:
        self.last_attempt = dt_util.utcnow()
        zone_entity_id = self.config_entry.data[CONF_ZONE]
        zone_state = self.hass.states.get(zone_entity_id)
        if zone_state is None:
            self.last_error_type = ERROR_UNKNOWN
            async_create_zone_removed_issue(self.hass, self.config_entry, zone_entity_id)
            raise UpdateFailed(f"Zone {zone_entity_id} bestaat niet (meer)")

        async_clear_zone_removed_issue(self.hass, self.config_entry)

        try:
            latitude = float(zone_state.attributes["latitude"])
            longitude = float(zone_state.attributes["longitude"])
        except (KeyError, TypeError, ValueError) as err:
            raise UpdateFailed(
                f"Zone {zone_entity_id} heeft geen geldige coördinaten"
            ) from err

        use_zone_radius = _get_config_value(
            self.config_entry, CONF_USE_ZONE_RADIUS, DEFAULT_USE_ZONE_RADIUS
        )
        if use_zone_radius:
            radius_m = float(zone_state.attributes.get("radius", DEFAULT_RADIUS_M))
        else:
            radius_m = float(
                _get_config_value(self.config_entry, CONF_RADIUS, DEFAULT_RADIUS_M)
            )

        max_results = int(
            _get_config_value(self.config_entry, CONF_MAX_RESULTS, DEFAULT_MAX_RESULTS)
        )
        connector_types_raw = _get_config_value(
            self.config_entry, CONF_CONNECTOR_TYPES, []
        )
        connector_types = (
            frozenset(ConnectorType(c) for c in connector_types_raw)
            if connector_types_raw
            else None
        )
        min_power_kw = float(
            _get_config_value(self.config_entry, CONF_MIN_POWER_KW, DEFAULT_MIN_POWER_KW)
        )

        try:
            result = await self.provider.async_get_locations(
                latitude=latitude,
                longitude=longitude,
                radius_m=radius_m,
                max_results=max_results,
                connector_types=connector_types,
                min_power_kw=min_power_kw,
            )
        except ProviderAuthError as err:
            self.last_error_type = ERROR_INVALID_AUTH
            self._register_failure()
            raise ConfigEntryAuthFailed(str(err)) from err
        except ProviderRateLimitedError as err:
            self.last_error_type = ERROR_RATE_LIMITED
            self._register_failure()
            raise UpdateFailed(f"Rate limit bereikt bij provider: {err}") from err
        except ProviderConnectionError as err:
            self.last_error_type = ERROR_CANNOT_CONNECT
            self._register_failure()
            raise UpdateFailed(f"Provider niet bereikbaar: {err}") from err
        except ProviderResponseError as err:
            self.last_error_type = ERROR_UNKNOWN
            self._register_failure()
            raise UpdateFailed(f"Ongeldige providerrespons: {err}") from err

        self.consecutive_failures = 0
        self.last_error_type = None
        async_clear_provider_unavailable_issue(self.hass, self.config_entry)

        self._check_tracked_entities()
        self._check_notification_target()

        sorted_locations = tuple(sorted(result.locations, key=_sort_key))[:max_results]

        return CoordinatorData(
            locations=sorted_locations,
            fetched_at=result.fetched_at,
            source_name=result.source_name,
            realtime_available=result.realtime_available,
            radius_m=radius_m,
        )

    def _register_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= UPDATE_FAILURE_STREAK_FOR_REPAIR:
            async_create_provider_unavailable_issue(self.hass, self.config_entry)

    def _check_tracked_entities(self) -> None:
        tracked_entities: list[str] = self.config_entry.data.get(
            CONF_TRACKED_ENTITIES, []
        )
        for entity_id in tracked_entities:
            if self.hass.states.get(entity_id) is None:
                async_create_tracked_entity_removed_issue(
                    self.hass, self.config_entry, entity_id
                )
            else:
                async_clear_tracked_entity_removed_issue(
                    self.hass, self.config_entry, entity_id
                )

    def _check_notification_target(self) -> None:
        notify_enabled = _get_config_value(
            self.config_entry, CONF_NOTIFY_ON_ZONE_ENTRY, False
        ) or _get_config_value(self.config_entry, CONF_NOTIFY_ON_AVAILABILITY_CHANGE, False)
        if not notify_enabled:
            async_clear_notification_service_missing_issue(self.hass, self.config_entry)
            return

        target = _get_config_value(self.config_entry, CONF_NOTIFICATION_TARGET, {})
        entity_ids = target.get("entity_id") if target else None
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        target_configured = bool(target and any(target.values()))
        target_valid = target_configured and (
            not entity_ids or all(self.hass.states.get(e) is not None for e in entity_ids)
        )

        if target_valid:
            async_clear_notification_service_missing_issue(self.hass, self.config_entry)
        else:
            async_create_notification_service_missing_issue(self.hass, self.config_entry)


def _get_config_value(config_entry: ConfigEntry, key: str, default):
    """Options overschrijven data; ontbrekende sleutel valt terug op default."""
    if key in config_entry.options:
        return config_entry.options[key]
    return config_entry.data.get(key, default)
