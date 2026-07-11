"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Optionele rijafstand-verrijking via de OpenRouteService Matrix API
(opt-in, bring-your-own-key). Hemelsbrede (Haversine) afstand blijft de
standaard voor filtering/sortering over de volledige resultatenlijst —
dit verrijkt uitsluitend de al-geselecteerde top-kandidaten met een echte
rijafstand, om het aantal externe API-calls laag te houden
(opdracht §20, performance-first op Raspberry Pi 4).

Bewust géén "provider" in de zin van providers/base.py: dit haalt geen
laadlocaties op, het verfijnt reeds genormaliseerde ChargeLocation-objecten.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from .api import ApiAuthError, ApiClient, ApiConnectionError, ApiRateLimitedError, ApiResponseError
from .const import ORS_MATRIX_URL_TEMPLATE, ORS_PROFILE_DRIVING
from .models import ChargeLocation

_LOGGER = logging.getLogger(__name__)


async def async_enrich_with_driving_distance(
    api_client: ApiClient,
    api_key: str,
    *,
    origin_lat: float,
    origin_lon: float,
    locations: tuple[ChargeLocation, ...],
) -> tuple[ChargeLocation, ...]:
    """Vervang de hemelsbrede afstand van `locations` door echte rijafstand.

    Faalt nooit hard: bij elke fout (auth, rate limit, netwerk, ongeldige
    respons) wordt een warning gelogd en de ongewijzigde invoer teruggegeven.
    Rijafstand is een verrijking, geen kritiek pad — een storing hier mag de
    coordinator-update nooit laten falen.
    """
    if not locations:
        return locations

    url = ORS_MATRIX_URL_TEMPLATE.format(profile=ORS_PROFILE_DRIVING)
    body = {
        "locations": [[origin_lon, origin_lat]]
        + [[loc.longitude, loc.latitude] for loc in locations],
        "sources": [0],
        "destinations": list(range(1, len(locations) + 1)),
        "metrics": ["distance"],
        "units": "m",
    }
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    try:
        payload = await api_client.async_post_json(url, json_body=body, headers=headers)
    except ApiAuthError:
        _LOGGER.warning(
            "OpenRouteService-key ongeldig of ontbreekt; val terug op hemelsbrede afstand"
        )
        return locations
    except ApiRateLimitedError:
        _LOGGER.warning("OpenRouteService rate limit bereikt; val terug op hemelsbrede afstand")
        return locations
    except ApiConnectionError:
        _LOGGER.warning("OpenRouteService niet bereikbaar; val terug op hemelsbrede afstand")
        return locations
    except ApiResponseError:
        _LOGGER.warning(
            "OpenRouteService gaf een ongeldige respons; val terug op hemelsbrede afstand"
        )
        return locations

    if not isinstance(payload, dict):
        _LOGGER.warning(
            "OpenRouteService-respons is geen JSON-object; val terug op hemelsbrede afstand"
        )
        return locations

    distances_matrix = payload.get("distances")
    if not isinstance(distances_matrix, list) or not distances_matrix:
        _LOGGER.warning(
            "OpenRouteService-respons mist een geldige 'distances'-matrix; "
            "val terug op hemelsbrede afstand"
        )
        return locations

    distances = distances_matrix[0]
    if not isinstance(distances, list) or len(distances) != len(locations):
        _LOGGER.warning(
            "OpenRouteService-afstandenlijst heeft een onverwachte lengte; "
            "val terug op hemelsbrede afstand"
        )
        return locations

    enriched: list[ChargeLocation] = []
    for location, distance in zip(locations, distances, strict=True):
        if not isinstance(distance, (int, float)):
            # Geen route gevonden voor deze locatie (bv. onbereikbaar per auto)
            # — behoud de hemelsbrede afstand voor die ene locatie.
            enriched.append(location)
            continue
        enriched.append(replace(location, distance_m=float(distance), distance_is_driving=True))
    return tuple(enriched)
