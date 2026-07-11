"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Centrale DataUpdateCoordinator — verzorgt providercommunicatie, filtering,
sortering, stale-datadetectie en foutafhandeling voor één config entry.
Alle entities lezen uitsluitend deze gedeelde dataset (opdracht §18).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance

from .api import ApiClient
from .const import (
    CONF_CONNECTOR_TYPES,
    CONF_MAX_DATA_AGE,
    CONF_MAX_RESULTS,
    CONF_MIN_POWER_KW,
    CONF_NOTIFICATION_TARGET,
    CONF_NOTIFY_ON_AVAILABILITY_CHANGE,
    CONF_NOTIFY_ON_ZONE_ENTRY,
    CONF_OPERATOR_EXCLUDE,
    CONF_ORS_API_KEY,
    CONF_RADIUS,
    CONF_ROUTE_CORRIDOR_M,
    CONF_ROUTE_DESTINATION_ZONE,
    CONF_TRACKED_ENTITIES,
    CONF_UPDATE_INTERVAL,
    CONF_USE_DRIVING_DISTANCE,
    CONF_USE_ZONE_RADIUS,
    CONF_ZONE,
    DEFAULT_MAX_DATA_AGE_MIN,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_POWER_KW,
    DEFAULT_RADIUS_M,
    DEFAULT_ROUTE_CORRIDOR_M,
    DEFAULT_UPDATE_INTERVAL_S,
    DEFAULT_USE_DRIVING_DISTANCE,
    DEFAULT_USE_ZONE_RADIUS,
    DOMAIN,
    DRIVING_DISTANCE_TOP_N,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_RATE_LIMITED,
    ERROR_UNKNOWN,
    ORS_BACKOFF_BASE_S,
    ORS_CONNECT_TIMEOUT_S,
    ORS_MAX_RETRIES,
    ORS_TOTAL_TIMEOUT_S,
    ROUTE_ENCLOSING_RADIUS_CAP_M,
    UPDATE_FAILURE_STREAK_FOR_REPAIR,
)
from .distance import async_enrich_with_driving_distance
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
from .route import Route, RouteError, async_fetch_route, distance_to_route_m

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
        self._ors_api_client = ApiClient(
            async_get_clientsession(hass),
            connect_timeout_s=ORS_CONNECT_TIMEOUT_S,
            total_timeout_s=ORS_TOTAL_TIMEOUT_S,
            max_retries=ORS_MAX_RETRIES,
            backoff_base_s=ORS_BACKOFF_BASE_S,
        )

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

        search_lat, search_lon, search_radius_m, route, corridor_m = (
            await self._async_resolve_search_area(latitude, longitude, zone_state)
        )

        try:
            result = await self.provider.async_get_locations(
                latitude=search_lat,
                longitude=search_lon,
                radius_m=search_radius_m,
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

        candidate_locations = result.locations
        if route is not None:
            candidate_locations = tuple(
                replace(
                    loc,
                    distance_m=ha_distance(latitude, longitude, loc.latitude, loc.longitude),
                )
                for loc in candidate_locations
                if distance_to_route_m(loc.latitude, loc.longitude, route) <= corridor_m
            )

        operator_exclude = {
            operator.strip().lower()
            for operator in _get_config_value(self.config_entry, CONF_OPERATOR_EXCLUDE, [])
            if operator.strip()
        }
        if operator_exclude:
            candidate_locations = tuple(
                loc
                for loc in candidate_locations
                if not (loc.operator and loc.operator.strip().lower() in operator_exclude)
            )

        sorted_locations = tuple(sorted(candidate_locations, key=_sort_key))
        sorted_locations = await self._async_apply_driving_distance(
            sorted_locations, latitude, longitude, max_results
        )
        sorted_locations = sorted_locations[:max_results]

        return CoordinatorData(
            locations=sorted_locations,
            fetched_at=result.fetched_at,
            source_name=result.source_name,
            realtime_available=result.realtime_available,
            radius_m=corridor_m if route is not None else search_radius_m,
        )

    async def _async_resolve_search_area(
        self, latitude: float, longitude: float, zone_state
    ) -> tuple[float, float, float, Route | None, float]:
        """Bepaal het zoekgebied: normale zone-radius, of routegebaseerd.

        Retourneert (search_lat, search_lon, search_radius_m, route, corridor_m).
        ``route`` is None en ``corridor_m`` is 0 in de normale (niet-route) modus.

        In tegenstelling tot de driving-distance-verrijking is er hier geen
        stille terugval: is er een routebestemming geconfigureerd maar
        mislukt de routeopvraging, dan faalt de hele update expliciet
        (``UpdateFailed``) — een radius-zoekopdracht tonen alsof het om een
        route ging zou de gebruiker misleiden.
        """
        destination_zone_id = _get_config_value(
            self.config_entry, CONF_ROUTE_DESTINATION_ZONE, None
        )
        if not destination_zone_id:
            use_zone_radius = _get_config_value(
                self.config_entry, CONF_USE_ZONE_RADIUS, DEFAULT_USE_ZONE_RADIUS
            )
            if use_zone_radius:
                radius_m = float(zone_state.attributes.get("radius", DEFAULT_RADIUS_M))
            else:
                radius_m = float(
                    _get_config_value(self.config_entry, CONF_RADIUS, DEFAULT_RADIUS_M)
                )
            return latitude, longitude, radius_m, None, 0.0

        destination_state = self.hass.states.get(destination_zone_id)
        if destination_state is None:
            async_create_zone_removed_issue(self.hass, self.config_entry, destination_zone_id)
            raise UpdateFailed(f"Routebestemming {destination_zone_id} bestaat niet (meer)")
        try:
            dest_lat = float(destination_state.attributes["latitude"])
            dest_lon = float(destination_state.attributes["longitude"])
        except (KeyError, TypeError, ValueError) as err:
            raise UpdateFailed(
                f"Routebestemming {destination_zone_id} heeft geen geldige coördinaten"
            ) from err

        ors_api_key = _get_config_value(self.config_entry, CONF_ORS_API_KEY, None)
        if not ors_api_key:
            self.last_error_type = ERROR_INVALID_AUTH
            raise UpdateFailed("Routegebaseerd zoeken vereist een OpenRouteService API-key")

        corridor_m = float(
            _get_config_value(
                self.config_entry, CONF_ROUTE_CORRIDOR_M, DEFAULT_ROUTE_CORRIDOR_M
            )
        )

        try:
            route = await async_fetch_route(
                self._ors_api_client,
                ors_api_key,
                origin_lat=latitude,
                origin_lon=longitude,
                destination_lat=dest_lat,
                destination_lon=dest_lon,
            )
        except RouteError as err:
            self.last_error_type = ERROR_CANNOT_CONNECT
            self._register_failure()
            raise UpdateFailed(f"Route kon niet berekend worden: {err}") from err

        search_radius_m = min(
            route.enclosing_radius_m + corridor_m, ROUTE_ENCLOSING_RADIUS_CAP_M
        )
        return route.center_latitude, route.center_longitude, search_radius_m, route, corridor_m

    async def _async_apply_driving_distance(
        self,
        sorted_locations: tuple[ChargeLocation, ...],
        latitude: float,
        longitude: float,
        max_results: int,
    ) -> tuple[ChargeLocation, ...]:
        """Verrijk de top-kandidaten met echte rijafstand (opt-in, OpenRouteService).

        Alleen de eerste ``min(DRIVING_DISTANCE_TOP_N, max_results)`` reeds op
        hemelsbrede afstand gesorteerde locaties krijgen een routeopvraging —
        dit begrenst het aantal externe calls per update (opdracht §20).
        """
        use_driving_distance = _get_config_value(
            self.config_entry, CONF_USE_DRIVING_DISTANCE, DEFAULT_USE_DRIVING_DISTANCE
        )
        ors_api_key = _get_config_value(self.config_entry, CONF_ORS_API_KEY, None)
        if not use_driving_distance or not ors_api_key or not sorted_locations:
            return sorted_locations

        enrich_count = min(DRIVING_DISTANCE_TOP_N, max_results, len(sorted_locations))
        top_candidates = sorted_locations[:enrich_count]
        remainder = sorted_locations[enrich_count:]

        enriched = await async_enrich_with_driving_distance(
            self._ors_api_client,
            ors_api_key,
            origin_lat=latitude,
            origin_lon=longitude,
            locations=top_candidates,
        )
        return tuple(sorted(enriched, key=_sort_key)) + remainder

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
