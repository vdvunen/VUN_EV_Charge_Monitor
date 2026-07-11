"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor het interne datamodel — met name de telsemantiek die
dubbeltelling van connectoren op dezelfde EVSE moet voorkomen.
"""

from __future__ import annotations

from custom_components.vun_ev_charge_monitor.models import (
    ChargeLocation,
    ChargePointStatus,
    Connector,
    ConnectorType,
    DataQuality,
    Evse,
)


def _make_location(evses: tuple[Evse, ...]) -> ChargeLocation:
    return ChargeLocation(
        provider="ndw",
        provider_location_id="loc-1",
        external_id=None,
        name="Test Locatie",
        latitude=52.37,
        longitude=4.89,
        address=None,
        postal_code=None,
        city=None,
        country="NL",
        operator="Test Operator",
        distance_m=250.0,
        navigation_url="https://example.invalid/nav",
        evses=evses,
        realtime_data_available=True,
        provider_status_raw=None,
        last_status_update=None,
        last_successful_update=None,
        source_quality=DataQuality.REALTIME,
    )


def test_evse_with_multiple_connectors_counts_once() -> None:
    """Eén EVSE met twee connectoren (Type2+CCS) mag niet dubbel tellen (opdracht §10)."""
    evse = Evse(
        evse_id="evse-1",
        status=ChargePointStatus.AVAILABLE,
        connectors=(
            Connector(connector_type=ConnectorType.TYPE_2, max_power_kw=22),
            Connector(connector_type=ConnectorType.CCS, max_power_kw=50),
        ),
    )
    location = _make_location((evse,))

    assert location.total_evses == 1
    assert location.available_evses == 1
    assert location.available_connectors == 1  # niet 2
    assert location.total_connectors == 2  # wel 2 (metadata, geen beschikbaarheid)
    assert location.max_power_kw == 50


def test_mixed_status_counts() -> None:
    evses = (
        Evse(evse_id="e1", status=ChargePointStatus.AVAILABLE, connectors=()),
        Evse(evse_id="e2", status=ChargePointStatus.OCCUPIED, connectors=()),
        Evse(evse_id="e3", status=ChargePointStatus.OUT_OF_ORDER, connectors=()),
        Evse(evse_id="e4", status=ChargePointStatus.UNKNOWN, connectors=()),
    )
    location = _make_location(evses)

    assert location.total_evses == 4
    assert location.available_evses == 1
    assert location.occupied_evses == 1
    assert location.out_of_order_evses == 1
    assert location.unknown_evses == 1
    assert location.is_available is True


def test_location_with_no_available_evses_is_not_available() -> None:
    evses = (Evse(evse_id="e1", status=ChargePointStatus.OCCUPIED, connectors=()),)
    location = _make_location(evses)

    assert location.is_available is False
    assert location.available_evses == 0


def test_unknown_status_never_counts_as_available() -> None:
    evses = (Evse(evse_id="e1", status=ChargePointStatus.UNKNOWN, connectors=()),)
    location = _make_location(evses)

    assert location.is_available is False


def test_connector_types_aggregated_across_evses() -> None:
    evses = (
        Evse(
            evse_id="e1",
            status=ChargePointStatus.AVAILABLE,
            connectors=(Connector(connector_type=ConnectorType.TYPE_2),),
        ),
        Evse(
            evse_id="e2",
            status=ChargePointStatus.AVAILABLE,
            connectors=(Connector(connector_type=ConnectorType.CCS),),
        ),
    )
    location = _make_location(evses)

    assert location.connector_types == frozenset({ConnectorType.TYPE_2, ConnectorType.CCS})
