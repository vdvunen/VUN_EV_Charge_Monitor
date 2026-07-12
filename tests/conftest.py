"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Gedeelde pytest-fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.vun_ev_charge_monitor.const import (
    CONF_CONNECTOR_TYPES,
    CONF_LANGUAGE,
    CONF_MAX_DATA_AGE,
    CONF_MAX_RESULTS,
    CONF_MIN_POWER_KW,
    CONF_NOTIFICATION_COOLDOWN,
    CONF_NOTIFICATION_TARGET,
    CONF_NOTIFY_ON_AVAILABILITY_CHANGE,
    CONF_NOTIFY_ON_ZONE_ENTRY,
    CONF_PROVIDER,
    CONF_RADIUS,
    CONF_SIMULATION_MODE,
    CONF_TRACKED_ENTITIES,
    CONF_UPDATE_INTERVAL,
    CONF_USE_ZONE_RADIUS,
    CONF_ZONE,
    DEFAULT_LANGUAGE,
    PROVIDER_NDW,
)

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Zorgt dat deze custom_component geladen kan worden tijdens tests."""
    yield


@pytest.fixture
def ndw_geojson_response() -> dict:
    """Voorbeeldrespons van de NDW DOT-NL bbox-API (geanonimiseerd testfixture)."""
    return json.loads((FIXTURES_DIR / "ndw_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def tomtom_response() -> dict:
    """Voorbeeldrespons van de TomTom EV Search API (geanonimiseerd testfixture)."""
    return json.loads((FIXTURES_DIR / "tomtom_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def ocm_response() -> list:
    """Voorbeeldrespons van de Open Charge Map API (geanonimiseerd testfixture)."""
    return json.loads((FIXTURES_DIR / "ocm_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def mock_config_entry_data() -> dict:
    """Volledige, geldige config entry data zoals door de config flow geproduceerd."""
    return {
        CONF_ZONE: "zone.woonwijk",
        CONF_PROVIDER: PROVIDER_NDW,
        "api_key": "",
        CONF_SIMULATION_MODE: False,
        CONF_TRACKED_ENTITIES: ["person.vincent"],
        CONF_USE_ZONE_RADIUS: False,
        CONF_RADIUS: 1500,
        CONF_MAX_RESULTS: 5,
        CONF_CONNECTOR_TYPES: [],
        CONF_MIN_POWER_KW: 0.0,
        CONF_UPDATE_INTERVAL: 300,
        CONF_MAX_DATA_AGE: 30,
        CONF_NOTIFICATION_TARGET: {},
        CONF_NOTIFY_ON_ZONE_ENTRY: True,
        CONF_NOTIFY_ON_AVAILABILITY_CHANGE: False,
        CONF_NOTIFICATION_COOLDOWN: 30,
        CONF_LANGUAGE: DEFAULT_LANGUAGE,
    }
