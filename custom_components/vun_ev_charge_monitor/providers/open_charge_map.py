"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Open Charge Map-provider (zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §1.3).
Uitsluitend statische locatie-/connectordata — OCM's `StatusType` is een
operationele status (werkend/kapot), geen actuele bezetting. Alle EVSE's
krijgen daarom status UNKNOWN, behalve wanneer `IsOperational` expliciet
`False` is (dan OUT_OF_ORDER). `realtime_data_available` staat altijd op
False (opdracht §10: "ontbrekende realtime data mag nooit als beschikbaar
worden weergegeven").

Vereist een gratis, door de gebruiker geregistreerde API-key (sinds kort
verplicht door OCM, zie FASE1-onderzoek §1.3).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance

from ..api import ApiAuthError, ApiClient, ApiConnectionError, ApiRateLimitedError, ApiResponseError
from ..const import OCM_API_URL
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

_MAX_QUANTITY_PER_CONNECTION = 20
"""Veiligheidsmarge tegen onrealistische/foutieve `Quantity`-waarden."""


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    return dt_util.parse_datetime(raw)


def _build_evses(connections: Any, poi_id: Any) -> tuple[Evse, ...]:
    if not isinstance(connections, list):
        return ()

    evses: list[Evse] = []
    evse_index = 0
    for connection in connections:
        if not isinstance(connection, dict):
            continue
        connection_type = connection.get("ConnectionType")
        type_title = (
            connection_type.get("Title") if isinstance(connection_type, dict) else None
        )
        connector_type = map_connector_type(type_title)

        power_raw = connection.get("PowerKW")
        try:
            power_kw = float(power_raw) if power_raw is not None else None
        except (TypeError, ValueError):
            power_kw = None

        try:
            quantity = int(connection.get("Quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1
        quantity = max(1, min(quantity, _MAX_QUANTITY_PER_CONNECTION))

        status_type = connection.get("StatusType")
        is_operational = (
            status_type.get("IsOperational") if isinstance(status_type, dict) else None
        )
        status = (
            ChargePointStatus.OUT_OF_ORDER
            if is_operational is False
            else ChargePointStatus.UNKNOWN
        )

        connector = Connector(connector_type=connector_type, max_power_kw=power_kw)
        for _ in range(quantity):
            evse_index += 1
            evses.append(
                Evse(
                    evse_id=f"{poi_id}-{evse_index}", status=status, connectors=(connector,)
                )
            )

    return tuple(evses)


def _poi_to_location(
    poi: dict[str, Any], *, origin_lat: float, origin_lon: float
) -> ChargeLocation | None:
    address_info = poi.get("AddressInfo")
    if not isinstance(address_info, dict):
        return None
    try:
        latitude = float(address_info["Latitude"])
        longitude = float(address_info["Longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None

    poi_id = poi.get("ID")
    if not poi_id:
        return None

    operator_info = poi.get("OperatorInfo")
    operator = (
        operator_info.get("Title") if isinstance(operator_info, dict) else None
    )
    country = address_info.get("Country")
    country_title = country.get("Title") if isinstance(country, dict) else None

    evses = _build_evses(poi.get("Connections"), poi_id)
    distance_m = ha_distance(origin_lat, origin_lon, latitude, longitude)

    return ChargeLocation(
        provider="open_charge_map",
        provider_location_id=str(poi_id),
        external_id=str(poi.get("UUID")) if poi.get("UUID") else None,
        name=str(address_info.get("Title") or operator or poi_id),
        latitude=latitude,
        longitude=longitude,
        address=address_info.get("AddressLine1"),
        postal_code=address_info.get("Postcode"),
        city=address_info.get("Town"),
        country=country_title,
        operator=operator,
        distance_m=distance_m,
        navigation_url=navigation_url(latitude, longitude),
        evses=evses,
        realtime_data_available=False,
        provider_status_raw=None,
        last_status_update=_parse_timestamp(poi.get("DateLastStatusUpdate")),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.STATIC,
        confidence_score=None,
    )


class OpenChargeMapProvider(ChargeLocationProvider):
    """Provider voor Open Charge Map — statische fallback (geen realtime data)."""

    name = "open_charge_map"

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
            raise ProviderAuthError(
                "Open Charge Map vereist een door de gebruiker aangeleverde API-key"
            )

        params = {
            "output": "json",
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "distance": f"{radius_m / 1000:.3f}",
            "distanceunit": "km",
            "maxresults": str(min(max(max_results * 4, 10), 100)),
        }
        headers = {"X-API-Key": self._api_key}

        try:
            payload = await self._api_client.async_get_json(
                OCM_API_URL, params=params, headers=headers
            )
        except ApiAuthError as err:
            raise ProviderAuthError(str(err)) from err
        except ApiRateLimitedError as err:
            raise ProviderRateLimitedError(str(err), err.retry_after) from err
        except ApiConnectionError as err:
            raise ProviderConnectionError(str(err)) from err
        except ApiResponseError as err:
            raise ProviderResponseError(str(err)) from err

        if not isinstance(payload, list):
            raise ProviderResponseError("Open Charge Map-respons is geen JSON-lijst")

        locations: list[ChargeLocation] = []
        skipped = 0
        for poi in payload:
            if not isinstance(poi, dict):
                skipped += 1
                continue
            location = _poi_to_location(poi, origin_lat=latitude, origin_lon=longitude)
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
            _LOGGER.debug("Open Charge Map: %d ongeldige/onvolledige records genegeerd", skipped)

        return ProviderFetchResult(
            locations=tuple(locations),
            source_name="Open Charge Map",
            fetched_at=dt_util.utcnow(),
            realtime_available=False,
        )
