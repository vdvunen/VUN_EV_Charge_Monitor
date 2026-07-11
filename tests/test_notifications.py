"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de notificatielogica: de drie meldingvarianten uit opdracht §3
(beschikbaar / niets beschikbaar / alleen statische data) in NL en EN, en
het daadwerkelijk versturen via `notify.send_message`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.coordinator import CoordinatorData
from custom_components.vun_ev_charge_monitor.models import (
    ChargeLocation,
    ChargePointStatus,
    DataQuality,
    Evse,
)
from custom_components.vun_ev_charge_monitor.notifications import (
    _build_message,
    async_send_charge_notification,
)


def _location(name: str, *, available: bool, distance_m: float, power_kw: float = 22.0) -> ChargeLocation:
    status = ChargePointStatus.AVAILABLE if available else ChargePointStatus.OCCUPIED
    return ChargeLocation(
        provider="ndw",
        provider_location_id=name,
        external_id=None,
        name=name,
        latitude=52.37,
        longitude=4.89,
        address=None,
        postal_code=None,
        city=None,
        country="NL",
        operator="Test Operator",
        distance_m=distance_m,
        navigation_url="https://example.invalid",
        evses=(Evse(evse_id=f"{name}-1", status=status, connectors=()),),
        realtime_data_available=True,
        provider_status_raw=None,
        last_status_update=dt_util.utcnow(),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME,
    )


def _coordinator_data(locations, *, realtime_available: bool = True, radius_m: float = 1500) -> CoordinatorData:
    return CoordinatorData(
        locations=tuple(locations),
        fetched_at=dt_util.utcnow(),
        source_name="NDW DOT-NL",
        realtime_available=realtime_available,
        radius_m=radius_m,
    )


def test_message_with_available_locations_nl() -> None:
    data = _coordinator_data([_location("P+R Centrum", available=True, distance_m=280)])
    message = _build_message(data, zone_name="Woonwijk", max_results=5, language="nl")

    assert "Laadpunten in de buurt van Woonwijk" in message
    assert "1 laadlocaties" in message
    assert "P+R Centrum" in message
    assert "1 van 1 beschikbaar" in message
    assert "280 meter afstand" in message
    assert "Bijgewerkt om" in message
    assert "NDW DOT-NL" in message


def test_message_with_available_locations_en() -> None:
    data = _coordinator_data([_location("P+R Centrum", available=True, distance_m=280)])
    message = _build_message(data, zone_name="Residential Area", max_results=5, language="en")

    assert "Charging locations near Residential Area" in message
    assert "1 of 1 available" in message
    assert "280 m away" in message
    assert "Updated at" in message


def test_message_no_availability_nl() -> None:
    data = _coordinator_data(
        [_location("P+R Centrum", available=False, distance_m=280)], radius_m=1500
    )
    message = _build_message(data, zone_name="Woonwijk", max_results=5, language="nl")

    assert "geen vrije laadpunten" in message
    assert "1,5 kilometer" in message
    assert "Woonwijk" in message


def test_message_no_availability_en() -> None:
    data = _coordinator_data(
        [_location("P+R Centrum", available=False, distance_m=280)], radius_m=1500
    )
    message = _build_message(data, zone_name="Residential Area", max_results=5, language="en")

    assert "no free charging points" in message
    assert "1.5 km" in message


def test_message_static_data_only_nl() -> None:
    data = _coordinator_data(
        [_location("P+R Centrum", available=True, distance_m=280)], realtime_available=False
    )
    message = _build_message(data, zone_name="Woonwijk", max_results=5, language="nl")

    assert "actuele bezetting is niet beschikbaar" in message
    assert "laadkabel" in message


def test_message_static_data_only_en() -> None:
    data = _coordinator_data(
        [_location("P+R Centrum", available=True, distance_m=280)], realtime_available=False
    )
    message = _build_message(data, zone_name="Residential Area", max_results=5, language="en")

    assert "occupancy data is unavailable" in message


def test_message_no_locations_found_nl() -> None:
    message = _build_message(_coordinator_data([]), zone_name="Woonwijk", max_results=5, language="nl")
    assert "geen laadlocaties gevonden" in message


def test_message_respects_max_results() -> None:
    locations = [
        _location(f"Locatie {i}", available=True, distance_m=100 * i) for i in range(1, 8)
    ]
    data = _coordinator_data(locations)
    message = _build_message(data, zone_name="Woonwijk", max_results=3, language="nl")

    assert "Locatie 1" in message
    assert "Locatie 3" in message
    assert "Locatie 4" not in message


async def test_send_notification_calls_notify_service(hass, mock_config_entry_data) -> None:
    data = {**mock_config_entry_data, "notification_target": {"entity_id": ["notify.mobile_app_test"]}}
    entry = MockConfigEntry(domain=DOMAIN, unique_id="zone.woonwijk", data=data)
    entry.add_to_hass(hass)
    hass.states.async_set(
        "zone.woonwijk", "zoning", {"latitude": 52.37, "longitude": 4.89, "friendly_name": "Woonwijk"}
    )

    coordinator_data = _coordinator_data([_location("P+R Centrum", available=True, distance_m=280)])

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
        await async_send_charge_notification(
            hass, entry, coordinator_data, language="nl", max_results=5
        )

    mock_call.assert_called_once()
    args, kwargs = mock_call.call_args
    assert args[0] == "notify"
    assert args[1] == "send_message"
    assert "P+R Centrum" in args[2]["message"]
    assert kwargs["target"] == {"entity_id": ["notify.mobile_app_test"]}


async def test_send_notification_skips_without_target(hass, mock_config_entry_data) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
        await async_send_charge_notification(hass, entry, None, language="nl", max_results=5)

    mock_call.assert_not_called()
