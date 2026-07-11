"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Routegebaseerd zoekgebied via de OpenRouteService Directions API
(gebruikersverzoek — laadpunten langs een route van A naar B in plaats van
alleen rond één zone-middelpunt).

Berekent de routegeometrie en een omsluitende zoekcirkel (middelpunt +
straal) die ongewijzigd aan de bestaande providerinterface
(`ChargeLocationProvider.async_get_locations`) wordt doorgegeven — er is
géén wijziging aan de providers zelf nodig. De coordinator filtert de
teruggekregen kandidaten vervolgens op werkelijke afstand tot de routelijn
(`distance_to_route_m`).

In tegenstelling tot de optionele rijafstand-verrijking (`distance.py`) is
dit géén "best effort met stille terugval" — zonder geldige route is
routegebaseerd zoeken zinloos, dus falen hier laat de coordinator-update
expliciet mislukken (`UpdateFailed`), met behoud van de laatst geldige data
zoals bij elke andere providerfout.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.util.location import distance as ha_distance

from .api import ApiClient
from .const import ORS_DIRECTIONS_URL_TEMPLATE, ORS_PROFILE_DRIVING

_LOGGER = logging.getLogger(__name__)


class RouteError(Exception):
    """De route kon niet berekend worden."""


@dataclass(frozen=True, slots=True)
class Route:
    """Een berekende route: geometrie plus een omsluitende zoekcirkel."""

    points: tuple[tuple[float, float], ...]
    """(latitude, longitude)-paren langs de route, in rijvolgorde."""
    center_latitude: float
    center_longitude: float
    enclosing_radius_m: float
    """Straal van de kleinste cirkel rond het middelpunt die alle routepunten bevat."""


async def async_fetch_route(
    api_client: ApiClient,
    api_key: str,
    *,
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> Route:
    """Haal de routegeometrie op tussen twee punten.

    Werpt ``RouteError`` bij elke fout (auth/rate-limit/netwerk/malformed) —
    er is bewust geen terugvalgedrag, zie moduledocstring.
    """
    url = ORS_DIRECTIONS_URL_TEMPLATE.format(profile=ORS_PROFILE_DRIVING)
    body = {"coordinates": [[origin_lon, origin_lat], [destination_lon, destination_lat]]}
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    try:
        payload = await api_client.async_post_json(url, json_body=body, headers=headers)
    except Exception as err:  # noqa: BLE001 - vertaald naar één domeinspecifieke fout
        raise RouteError(f"OpenRouteService-routeaanvraag mislukt ({type(err).__name__})") from err

    try:
        features = payload["features"]
        coordinates = features[0]["geometry"]["coordinates"]
    except (KeyError, IndexError, TypeError) as err:
        raise RouteError("Onverwachte structuur in OpenRouteService-routerespons") from err

    points: list[tuple[float, float]] = []
    for entry in coordinates:
        if (
            isinstance(entry, list)
            and len(entry) >= 2
            and all(isinstance(c, (int, float)) for c in entry[:2])
        ):
            points.append((float(entry[1]), float(entry[0])))  # (lat, lon)

    if not points:
        raise RouteError("OpenRouteService-route bevat geen geldige coördinaten")

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    center_lat = (min(lats) + max(lats)) / 2
    center_lon = (min(lons) + max(lons)) / 2
    enclosing_radius_m = max(
        ha_distance(center_lat, center_lon, lat, lon) for lat, lon in points
    )

    return Route(
        points=tuple(points),
        center_latitude=center_lat,
        center_longitude=center_lon,
        enclosing_radius_m=enclosing_radius_m,
    )


def distance_to_route_m(latitude: float, longitude: float, route: Route) -> float:
    """Kortste afstand van een punt tot de routelijn.

    Benadert de lijn als een reeks punten (i.p.v. exacte lijnstuk-projectie)
    — voldoende nauwkeurig gegeven de al elders gebruikte Haversine-
    benadering, en de routegeometrie van ORS bevat doorgaans genoeg punten
    (per bocht/richtingswijziging) om dit verschil verwaarloosbaar te maken.
    """
    return min(ha_distance(latitude, longitude, lat, lon) for lat, lon in route.points)
