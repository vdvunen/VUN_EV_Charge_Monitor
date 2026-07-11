"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Simulatieprovider (opdracht §27). Levert vaste, lokale testdata — geen
enkele externe API-call. Gebruikt wanneer een config entry `simulation_mode`
heeft ingeschakeld; de coordinator/entities blijven ongewijzigd, alleen de
provider wordt vervangen (zie `__init__.py`).

De gesimuleerde data is bewust divers zodat alle meldingvarianten uit
opdracht §3 getest kunnen worden door de zoekradius of connectorfilters in
de options flow aan te passen:
- "Sim P+R Centrum": deels beschikbaar;
- "Sim Supermarkt": volledig bezet;
- "Sim Snellader Ringweg": beschikbaar, hoog vermogen, CCS.
"""

from __future__ import annotations

from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance

from ..models import (
    ChargeLocation,
    ChargePointStatus,
    Connector,
    ConnectorType,
    DataQuality,
    Evse,
    ProviderFetchResult,
)
from .base import ChargeLocationProvider

_OFFSETS: tuple[tuple[str, float, float, tuple[Evse, ...]], ...] = (
    (
        "Sim P+R Centrum",
        0.0025,
        0.0010,
        (
            Evse(
                "sim-1-1",
                ChargePointStatus.AVAILABLE,
                (Connector(ConnectorType.TYPE_2, max_power_kw=22),),
            ),
            Evse(
                "sim-1-2",
                ChargePointStatus.AVAILABLE,
                (Connector(ConnectorType.TYPE_2, max_power_kw=22),),
            ),
            Evse(
                "sim-1-3",
                ChargePointStatus.OCCUPIED,
                (Connector(ConnectorType.TYPE_2, max_power_kw=22),),
            ),
        ),
    ),
    (
        "Sim Supermarkt",
        0.0037,
        -0.0020,
        (
            Evse(
                "sim-2-1",
                ChargePointStatus.OCCUPIED,
                (Connector(ConnectorType.TYPE_2, max_power_kw=11),),
            ),
            Evse(
                "sim-2-2",
                ChargePointStatus.OUT_OF_ORDER,
                (Connector(ConnectorType.TYPE_2, max_power_kw=11),),
            ),
        ),
    ),
    (
        "Sim Snellader Ringweg",
        -0.0110,
        0.0080,
        (
            Evse(
                "sim-3-1",
                ChargePointStatus.AVAILABLE,
                (Connector(ConnectorType.CCS, max_power_kw=150),),
            ),
            Evse(
                "sim-3-2",
                ChargePointStatus.AVAILABLE,
                (Connector(ConnectorType.CCS, max_power_kw=150),),
            ),
        ),
    ),
)


def _navigation_url(latitude: float, longitude: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&destination={latitude},{longitude}"


class SimulationProvider(ChargeLocationProvider):
    """Levert vaste, lokale testdata rond het opgegeven middelpunt."""

    name = "simulation"

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
        now = dt_util.utcnow()
        locations: list[ChargeLocation] = []

        for name, lat_offset, lon_offset, evses in _OFFSETS:
            loc_lat = latitude + lat_offset
            loc_lon = longitude + lon_offset
            dist = ha_distance(latitude, longitude, loc_lat, loc_lon)
            location = ChargeLocation(
                provider="simulation",
                provider_location_id=name.lower().replace(" ", "-"),
                external_id=None,
                name=name,
                latitude=loc_lat,
                longitude=loc_lon,
                address="Simulatieadres",
                postal_code=None,
                city="Simulatiestad",
                country="NL",
                operator="Simulatie",
                distance_m=dist,
                navigation_url=_navigation_url(loc_lat, loc_lon),
                evses=evses,
                realtime_data_available=True,
                provider_status_raw=None,
                last_status_update=now,
                last_successful_update=now,
                source_quality=DataQuality.REALTIME,
            )
            if location.distance_m is not None and location.distance_m > radius_m:
                continue
            if connector_types and not (location.connector_types & connector_types):
                continue
            if min_power_kw and (location.max_power_kw or 0) < min_power_kw:
                continue
            locations.append(location)

        return ProviderFetchResult(
            locations=tuple(locations[:max_results]),
            source_name="Simulatie",
            fetched_at=now,
            realtime_available=True,
        )
