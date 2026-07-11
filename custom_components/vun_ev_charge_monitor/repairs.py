"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Repair issues voor structurele problemen die de gebruiker zelf moet
oplossen (verwijderde zone/entity, langdurig onbereikbare provider).
Deze problemen zijn niet automatisch te herstellen binnen Home Assistant
(de gebruiker moet de zone/entity herstellen of de integratie
reconfigureren) — er wordt daarom bewust geen interactieve RepairsFlow
aangeboden (`is_fixable=False`), enkel een duidelijke melding met de
benodigde actie in de vertaalde issue-tekst.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    ISSUE_NOTIFICATION_SERVICE_MISSING,
    ISSUE_PROVIDER_UNAVAILABLE,
    ISSUE_TRACKED_ENTITY_REMOVED,
    ISSUE_ZONE_REMOVED,
)


def _issue_id(entry: ConfigEntry, kind: str, suffix: str | None = None) -> str:
    base = f"{entry.entry_id}_{kind}"
    return f"{base}_{suffix}" if suffix else base


def async_create_zone_removed_issue(
    hass: HomeAssistant, entry: ConfigEntry, zone_entity_id: str
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry, ISSUE_ZONE_REMOVED),
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_ZONE_REMOVED,
        translation_placeholders={"entry_title": entry.title, "zone": zone_entity_id},
    )


def async_clear_zone_removed_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry, ISSUE_ZONE_REMOVED))


def async_create_tracked_entity_removed_issue(
    hass: HomeAssistant, entry: ConfigEntry, entity_id: str
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry, ISSUE_TRACKED_ENTITY_REMOVED, entity_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_TRACKED_ENTITY_REMOVED,
        translation_placeholders={"entry_title": entry.title, "entity_id": entity_id},
    )


def async_clear_tracked_entity_removed_issue(
    hass: HomeAssistant, entry: ConfigEntry, entity_id: str
) -> None:
    ir.async_delete_issue(
        hass, DOMAIN, _issue_id(entry, ISSUE_TRACKED_ENTITY_REMOVED, entity_id)
    )


def async_create_provider_unavailable_issue(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry, ISSUE_PROVIDER_UNAVAILABLE),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_PROVIDER_UNAVAILABLE,
        translation_placeholders={"entry_title": entry.title},
    )


def async_clear_provider_unavailable_issue(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry, ISSUE_PROVIDER_UNAVAILABLE))


def async_create_notification_service_missing_issue(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry, ISSUE_NOTIFICATION_SERVICE_MISSING),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_NOTIFICATION_SERVICE_MISSING,
        translation_placeholders={"entry_title": entry.title},
    )


def async_clear_notification_service_missing_issue(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry, ISSUE_NOTIFICATION_SERVICE_MISSING))


def async_clear_all_issues_for_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Verwijder alle repair issues van deze config entry (bv. bij unload/removal).

    Voorkomt dat issues (inclusief de per-entity `tracked_entity_removed`-
    issues, die een onbegrensd aantal suffixen kunnen hebben) na verwijdering
    van de integratie als "spooksignalen" in de issue registry achterblijven
    (opdracht §36 rollback: "welke repair issues worden verwijderd").
    """
    registry = ir.async_get(hass)
    prefix = f"{entry.entry_id}_"
    stale_issue_ids = [
        issue.issue_id
        for issue in list(registry.issues.values())
        if issue.domain == DOMAIN and issue.issue_id.startswith(prefix)
    ]
    for issue_id in stale_issue_ids:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
