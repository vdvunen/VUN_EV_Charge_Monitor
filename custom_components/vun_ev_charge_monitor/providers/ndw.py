"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

NDW DOT-NL provider — primaire databron (zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md
§1.1 / §2). Haalt actuele laadpuntdata op via de bbox-GeoJSON API en
normaliseert deze naar het interne datamodel.

BELANGRIJKE AANNAMES (zie FASE1-onderzoek §7, te verifiëren voordat dit
richting v1.0.0 gaat):
1. Het exacte authenticatiemechanisme van de live dotnl.ndw.nu-API kon niet
   worden geverifieerd tegen publiek toegankelijke documentatie. Deze
   implementatie stuurt een optionele Bearer-token mee wanneer een API-key
   is geconfigureerd, en behandelt HTTP 401/403 als ongeldige auth. Werkt de
   API zonder key, dan functioneert dit pad ook zonder key.
2. NDW's live respons bevestigt alleen een geaggregeerd `available`/`total`
   per connectortype per locatie — geen bevestigde per-EVSE statusgranulariteit.
   Deze provider construeert daarom synthetische EVSE-records: `available`
   EVSE's met status AVAILABLE en (`total` - `available`) EVSE's met status
   OCCUPIED per connectorgroep. Dit is een bewuste, gedocumenteerde
   benadering — geen aanname die stilzwijgend als "zekere data" wordt
   gepresenteerd (`realtime_data_available` blijft desondanks True, omdat de
   aantallen zelf wel actueel/realtime zijn).
3. Exacte NDW-waarden voor `connector_type` zijn niet bevestigd; er wordt een
   defensieve, tolerante mapping gebruikt (substring-matching) die veilig
   terugvalt op ConnectorType.UNKNOWN bij onbekende waarden i.p.v. te crashen.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance

from ..api import ApiAuthError, ApiClient, ApiConnectionError, ApiRateLimitedError, ApiResponseError
from ..const import (
    NDW_API_BASE_URL,
    NDW_MAX_BBOX_DEGREES,
)
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


def _bbox_from_point(latitude: float, longitude: float, radius_m: float) -> str:
    """Bereken een rechthoekige bounding box rond een punt (native Python, geen GIS-dependency)."""
    radius_m = min(radius_m, 20_000)
    lat_delta = radius_m / 111_320
    lon_denominator = 111_320 * math.cos(math.radians(latitude))
    lon_delta = radius_m / lon_denominator if lon_denominator else lat_delta

    lat_delta = min(lat_delta, NDW_MAX_BBOX_DEGREES / 2)
    lon_delta = min(lon_delta, NDW_MAX_BBOX_DEGREES / 2)

    min_lat, max_lat = latitude - lat_delta, latitude + lat_delta
    min_lon, max_lon = longitude - lon_delta, longitude + lon_delta
    return f"{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}"


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    return dt_util.parse_datetime(raw)


def _build_evses(properties: dict[str, Any]) -> tuple[tuple[Evse, ...], bool]:
    """Bouw EVSE-records uit `availabilities[]`. Zie aanname 2 in moduledocstring."""
    availabilities = properties.get("availabilities")
    if not isinstance(availabilities, list) or not availabilities:
        return (), False

    evses: list[Evse] = []
    evse_index = 0
    for group in availabilities:
        if not isinstance(group, dict):
            continue
        try:
            total = int(group.get("total", 0))
            available = int(group.get("available", 0))
        except (TypeError, ValueError):
            continue
        if total < 0 or available < 0:
            continue
        available = min(available, total)

        connector_type = map_connector_type(group.get("connector_type"))
        power_max_raw = group.get("power_max")
        try:
            power_max = float(power_max_raw) if power_max_raw is not None else None
        except (TypeError, ValueError):
            power_max = None

        connector = Connector(connector_type=connector_type, max_power_kw=power_max)

        for _ in range(available):
            evse_index += 1
            evses.append(
                Evse(
                    evse_id=f"{properties.get('id', 'unknown')}-{evse_index}",
                    status=ChargePointStatus.AVAILABLE,
                    connectors=(connector,),
                )
            )
        for _ in range(total - available):
            evse_index += 1
            evses.append(
                Evse(
                    evse_id=f"{properties.get('id', 'unknown')}-{evse_index}",
                    status=ChargePointStatus.OCCUPIED,
                    connectors=(connector,),
                )
            )

    return tuple(evses), bool(evses)


def _feature_to_location(
    feature: dict[str, Any], *, origin_lat: float, origin_lon: float
) -> ChargeLocation | None:
    """Normaliseer één GeoJSON-feature naar ChargeLocation. Retourneert None bij ongeldige data."""
    geometry = feature.get("geometry")
    properties = feature.get("properties")
    if not isinstance(geometry, dict) or not isinstance(properties, dict):
        return None
    coordinates = geometry.get("coordinates")
    if (
        not isinstance(coordinates, list)
        or len(coordinates) < 2
        or not all(isinstance(c, (int, float)) for c in coordinates[:2])
    ):
        return None

    longitude, latitude = float(coordinates[0]), float(coordinates[1])
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None

    location_id = properties.get("id")
    if not location_id:
        return None

    evses, realtime_available = _build_evses(properties)
    distance_m = ha_distance(origin_lat, origin_lon, latitude, longitude)

    return ChargeLocation(
        provider="ndw",
        provider_location_id=str(location_id),
        external_id=str(properties.get("cpo_id")) if properties.get("cpo_id") else None,
        name=str(properties.get("operator_name") or properties.get("address") or location_id),
        latitude=latitude,
        longitude=longitude,
        address=str(properties.get("address")) if properties.get("address") else None,
        postal_code=None,
        city=None,
        country=str(properties.get("country")) if properties.get("country") else None,
        operator=str(properties.get("operator_name")) if properties.get("operator_name") else None,
        distance_m=distance_m,
        navigation_url=navigation_url(latitude, longitude),
        evses=evses,
        realtime_data_available=realtime_available,
        provider_status_raw=None,
        last_status_update=_parse_timestamp(properties.get("last_updated")),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME if realtime_available else DataQuality.UNKNOWN,
        confidence_score=None,
    )


class NdwProvider(ChargeLocationProvider):
    """Provider voor de NDW DOT-NL bbox-GeoJSON API."""

    name = "ndw"

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
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        bbox = _bbox_from_point(latitude, longitude, radius_m)

        try:
            payload = await self._api_client.async_get_json(
                NDW_API_BASE_URL, params={"bbox": bbox}, headers=headers
            )
        except ApiAuthError as err:
            raise ProviderAuthError(str(err)) from err
        except ApiRateLimitedError as err:
            raise ProviderRateLimitedError(str(err), err.retry_after) from err
        except ApiConnectionError as err:
            raise ProviderConnectionError(str(err)) from err
        except ApiResponseError as err:
            raise ProviderResponseError(str(err)) from err

        if not isinstance(payload, dict):
            raise ProviderResponseError("NDW-respons is geen JSON-object")

        features = payload.get("features")
        if not isinstance(features, list):
            raise ProviderResponseError("NDW-respons mist een geldige 'features'-lijst")

        # Verwerkingsplafond ter bescherming van de Raspberry Pi 4 (opdracht §20):
        # bbox is al server-side begrensd, dit is een extra veiligheidsmarge.
        processing_limit = max(max_results * 6, 50)

        locations: list[ChargeLocation] = []
        skipped = 0
        for feature in features[:processing_limit]:
            location = _feature_to_location(
                feature, origin_lat=latitude, origin_lon=longitude
            )
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
            _LOGGER.debug("NDW: %d ongeldige/onvolledige records genegeerd", skipped)

        return ProviderFetchResult(
            locations=tuple(locations),
            source_name="NDW DOT-NL",
            fetched_at=dt_util.utcnow(),
            realtime_available=any(loc.realtime_data_available for loc in locations),
        )
