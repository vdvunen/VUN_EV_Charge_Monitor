"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor routegebaseerd zoekgebied (OpenRouteService Directions API).
In tegenstelling tot distance.py faalt route.py altijd hard (RouteError) bij
problemen — er is bewust geen terugvalgedrag, zie moduledocstring in route.py.
"""

from __future__ import annotations

import pytest

from custom_components.vun_ev_charge_monitor.route import (
    Route,
    RouteError,
    async_fetch_route,
    distance_to_route_m,
)


class FakeApiClient:
    def __init__(self, payload=None, exception: Exception | None = None) -> None:
        self._payload = payload
        self._exception = exception
        self.last_url: str | None = None
        self.last_json_body: dict | None = None
        self.last_headers: dict | None = None

    async def async_post_json(self, url, json_body=None, headers=None):
        self.last_url = url
        self.last_json_body = json_body
        self.last_headers = headers
        if self._exception:
            raise self._exception
        return self._payload


def _geojson_payload(coordinates: list[list[float]]) -> dict:
    return {
        "features": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                }
            }
        ]
    }


async def test_successful_route_parses_points_and_computes_center() -> None:
    coordinates = [[5.0, 52.0], [5.1, 52.05], [5.2, 52.0]]
    client = FakeApiClient(payload=_geojson_payload(coordinates))

    route = await async_fetch_route(
        client,
        "key",
        origin_lat=52.0,
        origin_lon=5.0,
        destination_lat=52.0,
        destination_lon=5.2,
    )

    assert isinstance(route, Route)
    assert route.points == ((52.0, 5.0), (52.05, 5.1), (52.0, 5.2))
    assert route.center_latitude == pytest.approx((52.0 + 52.05) / 2)
    assert route.center_longitude == pytest.approx((5.0 + 5.2) / 2)
    assert route.enclosing_radius_m > 0


async def test_request_body_uses_lon_lat_order() -> None:
    client = FakeApiClient(payload=_geojson_payload([[5.0, 52.0], [5.2, 52.1]]))

    await async_fetch_route(
        client,
        "key",
        origin_lat=52.0,
        origin_lon=5.0,
        destination_lat=52.1,
        destination_lon=5.2,
    )

    assert client.last_json_body["coordinates"] == [[5.0, 52.0], [5.2, 52.1]]
    assert client.last_headers["Authorization"] == "key"


async def test_transport_failure_raises_route_error() -> None:
    client = FakeApiClient(exception=ConnectionError("down"))

    with pytest.raises(RouteError):
        await async_fetch_route(
            client,
            "key",
            origin_lat=52.0,
            origin_lon=5.0,
            destination_lat=52.1,
            destination_lon=5.2,
        )


async def test_empty_features_raises_route_error() -> None:
    client = FakeApiClient(payload={"features": []})

    with pytest.raises(RouteError):
        await async_fetch_route(
            client,
            "key",
            origin_lat=52.0,
            origin_lon=5.0,
            destination_lat=52.1,
            destination_lon=5.2,
        )


async def test_missing_geometry_raises_route_error() -> None:
    client = FakeApiClient(payload={"features": [{}]})

    with pytest.raises(RouteError):
        await async_fetch_route(
            client,
            "key",
            origin_lat=52.0,
            origin_lon=5.0,
            destination_lat=52.1,
            destination_lon=5.2,
        )


async def test_no_valid_coordinates_raises_route_error() -> None:
    client = FakeApiClient(payload=_geojson_payload([["not", "numeric"]]))

    with pytest.raises(RouteError):
        await async_fetch_route(
            client,
            "key",
            origin_lat=52.0,
            origin_lon=5.0,
            destination_lat=52.1,
            destination_lon=5.2,
        )


def test_distance_to_route_m_finds_closest_point() -> None:
    route = Route(
        points=((52.0, 5.0), (52.1, 5.0), (52.2, 5.0)),
        center_latitude=52.1,
        center_longitude=5.0,
        enclosing_radius_m=15000.0,
    )

    # Punt vlak bij het middelste routepunt (52.1, 5.0)
    d = distance_to_route_m(52.1001, 5.0, route)

    assert d < 200.0


def test_distance_to_route_m_far_from_route_is_large() -> None:
    route = Route(
        points=((52.0, 5.0), (52.1, 5.0)),
        center_latitude=52.05,
        center_longitude=5.0,
        enclosing_radius_m=6000.0,
    )

    d = distance_to_route_m(53.0, 6.0, route)

    assert d > 50000.0
