"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Notificatielogica (opdracht §16). Bouwt de meldingtekst in het Nederlands
of Engels op basis van de coordinatordata en verstuurt deze via de door de
gebruiker geconfigureerde `notify`-entiteit(en)/apparaat(en)/gebied(en).

De drie meldingvarianten uit opdracht §3 (beschikbaar / niets beschikbaar /
alleen statische data) worden hier expliciet onderscheiden — nooit
alsnog "beschikbaar" tonen wanneer realtime data ontbreekt.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.util import dt as dt_util

from .const import CONF_NOTIFICATION_TARGET, CONF_ZONE, DEFAULT_MAX_RESULTS
from .coordinator import CoordinatorData
from .models import ChargeLocation, ConnectorType

_LOGGER = logging.getLogger(__name__)

_CONNECTOR_LABELS: dict[str, dict[ConnectorType, str]] = {
    "nl": {
        ConnectorType.TYPE_2: "Type 2",
        ConnectorType.CCS: "CCS",
        ConnectorType.CHADEMO: "CHAdeMO",
        ConnectorType.TYPE_1: "Type 1",
        ConnectorType.DOMESTIC: "Huishoudstekker",
        ConnectorType.UNKNOWN: "Onbekend",
    },
    "en": {
        ConnectorType.TYPE_2: "Type 2",
        ConnectorType.CCS: "CCS",
        ConnectorType.CHADEMO: "CHAdeMO",
        ConnectorType.TYPE_1: "Type 1",
        ConnectorType.DOMESTIC: "Domestic socket",
        ConnectorType.UNKNOWN: "Unknown",
    },
}


def _format_distance(distance_m: float | None, language: str) -> str:
    if distance_m is None:
        return ""
    if distance_m >= 1000:
        km = distance_m / 1000
        value = f"{km:.1f}"
        if language == "nl":
            value = value.replace(".", ",")
            return f"{value} kilometer"
        return f"{value} km"
    meters = round(distance_m)
    return f"{meters} meter" if language == "nl" else f"{meters} m"


def _connector_label(location: ChargeLocation, language: str) -> str:
    labels = _CONNECTOR_LABELS.get(language, _CONNECTOR_LABELS["en"])
    types = sorted(
        (t for t in location.connector_types if t is not ConnectorType.UNKNOWN),
        key=lambda t: t.value,
    )
    if not types:
        return labels[ConnectorType.UNKNOWN]
    return "/".join(labels[t] for t in types)


def _format_location_block(index: int, location: ChargeLocation, language: str) -> str:
    distance = _format_distance(location.distance_m, language)
    power = f"{location.max_power_kw:g}" if location.max_power_kw else "?"
    connector = _connector_label(location, language)
    if language == "nl":
        return (
            f"{index}. {location.name}\n"
            f"   {location.available_evses} van {location.total_evses} beschikbaar\n"
            f"   {connector} · maximaal {power} kW\n"
            f"   {distance} afstand"
        )
    return (
        f"{index}. {location.name}\n"
        f"   {location.available_evses} of {location.total_evses} available\n"
        f"   {connector} · max {power} kW\n"
        f"   {distance} away"
    )


def _build_message(
    data: CoordinatorData | None, *, zone_name: str, max_results: int, language: str
) -> str:
    now_str = dt_util.now().strftime("%H:%M")

    if data is None or data.total_location_count == 0:
        if language == "nl":
            return (
                f"Er zijn geen laadlocaties gevonden binnen de ingestelde radius "
                f"van {zone_name}.\n\nDe status is voor het laatst bijgewerkt om {now_str}."
            )
        return (
            f"No charging locations were found within the configured radius of "
            f"{zone_name}.\n\nStatus last updated at {now_str}."
        )

    if not data.realtime_available:
        if language == "nl":
            return (
                f"Er zijn {data.total_location_count} laadlocaties gevonden, maar de "
                "actuele bezetting is niet beschikbaar.\n\n"
                "Controleer voor vertrek de laadpaalapp voordat je de laadkabel "
                "alvast enthousiast uit de kofferbak haalt."
            )
        return (
            f"{data.total_location_count} charging locations were found, but current "
            "occupancy data is unavailable.\n\n"
            "Check the charging app before enthusiastically grabbing the cable "
            "from the trunk."
        )

    if data.available_location_count == 0:
        radius_label = _format_distance(data.radius_m, language)
        if language == "nl":
            return (
                f"Er zijn momenteel geen vrije laadpunten binnen {radius_label} van "
                f"{zone_name}.\n\nDe status is voor het laatst bijgewerkt om {now_str}."
            )
        return (
            f"There are currently no free charging points within {radius_label} of "
            f"{zone_name}.\n\nStatus last updated at {now_str}."
        )

    top_locations = data.locations[:max_results]
    blocks = "\n\n".join(
        _format_location_block(i, loc, language) for i, loc in enumerate(top_locations, start=1)
    )
    if language == "nl":
        header = (
            f"Laadpunten in de buurt van {zone_name}\n\n"
            f"Er zijn {data.available_location_count} laadlocaties met in totaal "
            f"{data.available_connector_count} vrije aansluitingen."
        )
        footer = f"Bijgewerkt om {now_str} via {data.source_name}."
    else:
        header = (
            f"Charging locations near {zone_name}\n\n"
            f"There are {data.available_location_count} charging locations with a "
            f"total of {data.available_connector_count} free connectors."
        )
        footer = f"Updated at {now_str} via {data.source_name}."

    return f"{header}\n\n{blocks}\n\n{footer}"


async def async_send_charge_notification(
    hass: HomeAssistant,
    entry: ConfigEntry,
    data: CoordinatorData | None,
    *,
    language: str,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> None:
    """Bouw en verstuur de laadpuntmelding via de geconfigureerde notify-target."""
    target = entry.data.get(CONF_NOTIFICATION_TARGET) or entry.options.get(
        CONF_NOTIFICATION_TARGET
    )
    if not target or not any(target.values()):
        _LOGGER.debug("Geen notificatiedoel geconfigureerd, melding overgeslagen")
        return

    zone_state = hass.states.get(entry.data[CONF_ZONE])
    zone_name = zone_state.name if zone_state else entry.data[CONF_ZONE]

    message = _build_message(
        data,
        zone_name=zone_name,
        max_results=max_results or DEFAULT_MAX_RESULTS,
        language=language,
    )

    try:
        await hass.services.async_call(
            "notify",
            "send_message",
            {"message": message},
            target=target,
            blocking=True,
        )
    except ServiceNotFound:
        _LOGGER.warning(
            "Kon melding niet versturen: notificatiedoel is niet (meer) beschikbaar"
        )
    except HomeAssistantError as err:
        _LOGGER.warning("Kon melding niet versturen: %s", err)
