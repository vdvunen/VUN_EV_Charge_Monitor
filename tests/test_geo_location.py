"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de kaartmarker-entiteiten (geo_location-platform): kleurlogica
op basis van beschikbaarheid, en lege-slot-gedrag.
"""

from __future__ import annotations

from homeassistant.util import dt as dt_util

from custom_components.vun_ev_charge_monitor.const import DOMAIN
from custom_components.vun_ev_charge_monitor.geo_location import (
    VunEvChargeLocationMarker,
    _marker_picture,
)
from custom_components.vun_ev_charge_monitor.models import (
    ChargeLocation,
    ChargePointStatus,
    DataQuality,
    Evse,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _location(name: str, available_count: int, total_count: int) -> ChargeLocation:
    evses = tuple(
        Evse(f"{name}-{i}", ChargePointStatus.AVAILABLE if i < available_count else ChargePointStatus.OCCUPIED, ())
        for i in range(total_count)
    )
    return ChargeLocation(
        provider="ndw",
        provider_location_id=name,
        external_id=None,
        name=name,
        latitude=52.37,
        longitude=4.89,
        address="Teststraat 1",
        postal_code=None,
        city=None,
        country="NL",
        operator="Test Operator",
        distance_m=100.0,
        navigation_url="https://example.invalid",
        evses=evses,
        realtime_data_available=True,
        provider_status_raw=None,
        last_status_update=dt_util.utcnow(),
        last_successful_update=dt_util.utcnow(),
        source_quality=DataQuality.REALTIME,
    )


def test_marker_picture_red_when_nothing_available() -> None:
    assert _marker_picture(0) == "/vun_ev_charge_monitor_markers/marker-red.png"


def test_marker_picture_orange_when_one_available() -> None:
    assert _marker_picture(1) == "/vun_ev_charge_monitor_markers/marker-orange.png"


def test_marker_picture_green_when_two_or_more_available() -> None:
    assert _marker_picture(2) == "/vun_ev_charge_monitor_markers/marker-green.png"
    assert _marker_picture(10) == "/vun_ev_charge_monitor_markers/marker-green.png"


class _FakeCoordinatorData:
    def __init__(self, locations) -> None:
        self.locations = locations


class _FakeCoordinator:
    def __init__(self, hass, locations) -> None:
        self.data = _FakeCoordinatorData(locations)
        self.config_entry = MockConfigEntry(domain=DOMAIN, data={})
        self.config_entry.add_to_hass(hass)


def test_marker_reflects_current_slot_location(hass) -> None:
    location = _location("P+R Centrum", available_count=2, total_count=2)
    coordinator = _FakeCoordinator(hass, [location])
    marker = VunEvChargeLocationMarker(coordinator, 0)

    assert marker.available is True
    assert marker.name == "P+R Centrum"
    assert marker.latitude == 52.37
    assert marker.longitude == 4.89
    assert marker.distance == 0.1
    assert marker.entity_picture == "/vun_ev_charge_monitor_markers/marker-green.png"
    assert marker.extra_state_attributes["available_connectors"] == 2


def test_marker_unavailable_when_slot_empty(hass) -> None:
    coordinator = _FakeCoordinator(hass, [])
    marker = VunEvChargeLocationMarker(coordinator, 0)

    assert marker.available is False
    assert marker.latitude is None
    assert marker.entity_picture is None
    assert marker.extra_state_attributes is None


def test_marker_color_updates_with_occupancy(hass) -> None:
    fully_occupied = _location("Bezet Station", available_count=0, total_count=2)
    coordinator = _FakeCoordinator(hass, [fully_occupied])
    marker = VunEvChargeLocationMarker(coordinator, 0)

    assert marker.entity_picture == "/vun_ev_charge_monitor_markers/marker-red.png"
