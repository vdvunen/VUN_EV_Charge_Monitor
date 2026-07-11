"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

TomTom EV Search-provider (zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §1.2).
Alleen actief wanneer de gebruiker een eigen API-key configureert
(opdracht §7.2/§8) — geen gratis tier voor deze API, dus nooit als
standaardprovider gebruikt.

In tegenstelling tot NDW levert TomTom's EV Search-respons per laadpunt al
een `status` (Available/Occupied/Reserved/OutOfService/Unknown) via
`chargingStations[].chargingPoints[]` — dit wordt direct 1-op-1 gemapt naar
EVSE-records, zonder de synthetische benadering die voor NDW nodig was.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance

from ..api import ApiAuthError, ApiClient, ApiConnectionError, ApiRateLimitedError, ApiResponseError
from ..const import TOMTOM_SEARCH_URL
from ..models import (
    ChargeLocation,
    ChargePointStatus,
    Connector,
    ConnectorType,
    DataQuality,
    Evse,
    ProviderFetchResult,
)
from ._common import map_connector_type, navigation_url, passes_filters
from .base import (
    ChargeLocationProvider,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitedError,
    ProviderResponseError,
)

_LOGGER = logging.getLogger(__name__)

_STATUS_MAP: dict[str, ChargePointStatus] = {
    "available": ChargePointStatus.AVAILABLE,
    "occupied": ChargePointStatus.OCCUPIED,
    "reserved": ChargePointStatus.RESERVED,
    "outofservice": ChargePointStatus.OUT_OF_ORDER,
    "unknown": ChargePointStatus.UNKNOWN,
}


def _map_status(raw: Any) -> ChargePointStatus:
    if not isinstance(raw, str):
        return ChargePointStatus.UNKNOWN
    return _STATUS_MAP.get(raw.strip().lower(), ChargePointStatus.UNKNOWN)


def _build_evses(charging_points: Any) -> tuple[Evse, ...]:
    if not isinstance(charging_points, list):
        return ()

    evses: list[Evse] = []
    for index, point in enumerate(charging_points):
        if not isinstance(point, dict):
            continue
        point_id = str(point.get("evseId") or point.get("id") or f"tomtom-{index}")
        status = _map_status(point.get("status"))

        connectors: list[Connector] = []
        for connector_raw in point.get("connectors") or []:
            if not isinstance(connector_raw, dict):
                continue
            connector_type = map_connector_type(connector_raw.get("type"))
            power_raw = connector_raw.get("ratedPowerKW")
            try:
                power_kw = float(power_raw) if power_raw is not None else None
            except (TypeError, ValueError):
                power_kw = None
            connectors.append(Connector(connector_type=connector_type, max_power_kw=power_kw))

        evses.append(Evse(evse_id=point_id, status=status, connectors=tuple(connectors)))

    return tuple(evses)


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    return dt_util.parse_datetime(raw)


def _result_to_location(
    result: dict[str, Any], *, origin_lat: float, origin_lon: float
) -> ChargeLocation | None:
    position = result.get("position")
    if not isinstance(position, dict):
        return None
    try:
        latitude = float(position["lat"])
        longitude = float(position["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None

    result_id = result.get("id")
    if not result_id:
        return None

    poi = result.get("poi") if isinstance(result.get("poi"), dict) else {}
    address = result.get("address") if isinstance(result.get("address"), dict) else {}

    charging_stations = result.get("chargingStations")
    evses: tuple[Evse, ...] = ()
    if isinstance(charging_stations, list):
        for station in charging_stations:
            if isinstance(station, dict):
                evses += _build_evses(station.get("chargingPoints"))

    distance_m = ha_distance(origin_lat, origin_lon, latitude, longitude)
    realtime_available = bool(evses)

    return ChargeLocation(
        provider="tomtom",
        provider_location_id=str(result_id),
        external_id=None,
        name=str(poi.get("name") or address.get("freeformAddress") or result_id),
        latitude=latitude,
        longitude=longitude,
        address=address.get("freeformAddress"),
        postal_code=address.get("postalCode"),
        city=address.get("municipality"),
        country=address.get("country"),
        operator=str(poi.get("brands", [{}])[0].get("name")) if poi.get("brands") else None,
        distance_m=distance_m,
        navigation_url=navigation_url(latitude, longitude),
        evses=evses,
        realtime_data_available=realtime_available,
        provider_status_raw=None,
        last_status_update=_parse_timestamp(result.get("lastUpdateTime")),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME if realtime_available else DataQuality.UNKNOWN,
        confidence_score=None,
    )


class TomTomProvider(ChargeLocationProvider):
    """Provider voor de TomTom EV Search API."""

    name = "tomtom"

    def __init__(self, api_client: ApiClient, *, api_key: str | None = None) -> None:
        self._api_client = api_client
        self._api_key = api_key

    async def async_get_locations(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_m: float,
        max_results: int,
        connector_types: frozenset[ConnectorType] | None = None,
        min_power_kw: float = 0.0,
    ) -> ProviderFetchResult:
        if not self._api_key:
            raise ProviderAuthError("TomTom vereist een door de gebruiker aangeleverde API-key")

        params = {
            "key": self._api_key,
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "radius": str(min(int(radius_m), 50_000)),
            "limit": str(min(max(max_results, 1), 100)),
        }

        try:
            payload = await self._api_client.async_get_json(TOMTOM_SEARCH_URL, params=params)
        except ApiAuthError as err:
            raise ProviderAuthError(str(err)) from err
        except ApiRateLimitedError as err:
            raise ProviderRateLimitedError(str(err), err.retry_after) from err
        except ApiConnectionError as err:
            raise ProviderConnectionError(str(err)) from err
        except ApiResponseError as err:
            raise ProviderResponseError(str(err)) from err

        if not isinstance(payload, dict):
            raise ProviderResponseError("TomTom-respons is geen JSON-object")

        results = payload.get("results")
        if not isinstance(results, list):
            raise ProviderResponseError("TomTom-respons mist een geldige 'results'-lijst")

        locations: list[ChargeLocation] = []
        skipped = 0
        for result in results:
            if not isinstance(result, dict):
                skipped += 1
                continue
            location = _result_to_location(result, origin_lat=latitude, origin_lon=longitude)
            if location is None:
                skipped += 1
                continue
            if not passes_filters(
                location,
                radius_m=radius_m,
                connector_types=connector_types,
                min_power_kw=min_power_kw,
            ):
                continue
            locations.append(location)

        if skipped:
            _LOGGER.debug("TomTom: %d ongeldige/onvolledige records genegeerd", skipped)

        return ProviderFetchResult(
            locations=tuple(locations),
            source_name="TomTom",
            fetched_at=dt_util.utcnow(),
            realtime_available=any(loc.realtime_data_available for loc in locations),
        )
