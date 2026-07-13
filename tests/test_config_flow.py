"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Tests voor de config flow en options flow. De providerverbinding wordt
gemockt zodat er geen echte netwerkcalls plaatsvinden tijdens tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vun_ev_charge_monitor.const import DOMAIN

_USER_STEP_INPUT = {"zone": "zone.woonwijk", "provider": "ndw", "api_key": ""}
_TRACKING_STEP_INPUT = {"tracked_entities": ["person.vincent"]}
_SEARCH_STEP_INPUT = {
    "use_zone_radius": False,
    "radius": 1500,
    "max_results": 5,
    "connector_types": [],
    "min_power_kw": 0.0,
    "update_interval": 300,
    "max_data_age": 30,
}
_NOTIFICATIONS_STEP_INPUT = {
    "notification_target": {},
    "notify_on_zone_entry": True,
    "notify_on_availability_change": False,
    "notification_cooldown": 30,
    "language": "nl",
}


def _set_zone_and_person(hass) -> None:
    hass.states.async_set(
        "zone.woonwijk",
        "zoning",
        {"latitude": 52.37, "longitude": 4.89, "radius": 100, "friendly_name": "Woonwijk"},
    )
    hass.states.async_set("person.vincent", "home")


async def test_full_config_flow_creates_entry(hass) -> None:
    _set_zone_and_person(hass)

    with patch(
        "custom_components.vun_ev_charge_monitor.config_flow._async_test_provider_connection",
        AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _USER_STEP_INPUT
        )
        assert result["step_id"] == "tracking"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _TRACKING_STEP_INPUT
        )
        assert result["step_id"] == "search"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _SEARCH_STEP_INPUT
        )
        assert result["step_id"] == "notifications"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _NOTIFICATIONS_STEP_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Woonwijk"
    assert result["data"]["zone"] == "zone.woonwijk"
    assert result["data"]["tracked_entities"] == ["person.vincent"]


async def test_invalid_zone_shows_error(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"zone": "zone.does_not_exist", "provider": "ndw", "api_key": ""}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_zone"}


async def test_cannot_connect_shows_error(hass) -> None:
    _set_zone_and_person(hass)

    with patch(
        "custom_components.vun_ev_charge_monitor.config_flow._async_test_provider_connection",
        AsyncMock(return_value="cannot_connect"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _USER_STEP_INPUT
        )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_zone_aborts(hass) -> None:
    _set_zone_and_person(hass)
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="zone.woonwijk",
        data={"zone": "zone.woonwijk"},
    ).add_to_hass(hass)

    with patch(
        "custom_components.vun_ev_charge_monitor.config_flow._async_test_provider_connection",
        AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _USER_STEP_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_missing_tracked_entity_shows_error(hass) -> None:
    _set_zone_and_person(hass)

    with patch(
        "custom_components.vun_ev_charge_monitor.config_flow._async_test_provider_connection",
        AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _USER_STEP_INPUT
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"tracked_entities": []}
        )

    assert result["step_id"] == "tracking"
    assert result["errors"] == {"base": "invalid_entity"}


async def test_reconfigure_updates_options_not_shadowed(
    hass, mock_config_entry_data
) -> None:
    """Regressie: options (eerder gezet via Configureren) overschaduwden
    reconfigure-wijzigingen omdat _get_config_value options voorrang geeft
    boven data, terwijl reconfigure alleen naar data schreef."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="zone.woonwijk",
        data=mock_config_entry_data,
        options=mock_config_entry_data,
    )
    entry.add_to_hass(hass)
    _set_zone_and_person(hass)

    with patch(
        "custom_components.vun_ev_charge_monitor.config_flow._async_test_provider_connection",
        AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _USER_STEP_INPUT
        )
        assert result["step_id"] == "tracking"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _TRACKING_STEP_INPUT
        )
        assert result["step_id"] == "search"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**_SEARCH_STEP_INPUT, "update_interval": 900}
        )
        assert result["step_id"] == "notifications"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _NOTIFICATIONS_STEP_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.options["update_interval"] == 900
    assert entry.data["update_interval"] == 900


async def test_options_flow_updates_radius(hass, mock_config_entry_data) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="zone.woonwijk", data=mock_config_entry_data
    )
    entry.add_to_hass(hass)
    _set_zone_and_person(hass)

    with patch(
        "custom_components.vun_ev_charge_monitor.config_flow._async_test_provider_connection",
        AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], _USER_STEP_INPUT
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], _TRACKING_STEP_INPUT
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**_SEARCH_STEP_INPUT, "radius": 3000}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], _NOTIFICATIONS_STEP_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["radius"] == 3000
