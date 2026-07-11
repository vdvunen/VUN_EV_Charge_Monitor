"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Button-entiteiten: handmatig vernieuwen en een testmelding versturen
(opdracht §17/§26/§27 — voorkeur button entity boven een custom service).
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LANGUAGE, CONF_MAX_RESULTS, DEFAULT_LANGUAGE, DEFAULT_MAX_RESULTS
from .coordinator import VunEvChargeMonitorCoordinator
from .entity import VunEvChargeMonitorEntity
from .notifications import async_send_charge_notification


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [VunEvRefreshButton(coordinator), VunEvTestNotificationButton(coordinator, entry)]
    )


class VunEvRefreshButton(VunEvChargeMonitorEntity, ButtonEntity):
    """Forceert een directe coordinator-refresh."""

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator) -> None:
        super().__init__(coordinator, "refresh")

    @property
    def available(self) -> bool:
        # De refreshknop moet altijd bruikbaar zijn, ook zonder eerdere data.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class VunEvTestNotificationButton(VunEvChargeMonitorEntity, ButtonEntity):
    """Verstuurt direct een melding met de huidige data, los van cooldown/toggles.

    Bedoeld om de notificatie-configuratie te verifiëren (opdracht §27
    "kan een testmelding worden verstuurd") zonder op een echte zone-entry
    te hoeven wachten.
    """

    _attr_translation_key = "send_test_notification"
    _attr_icon = "mdi:message-alert-outline"

    def __init__(self, coordinator: VunEvChargeMonitorCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, "send_test_notification")
        self._entry = entry

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        language = self._entry.options.get(
            CONF_LANGUAGE, self._entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        )
        max_results = self._entry.options.get(
            CONF_MAX_RESULTS, self._entry.data.get(CONF_MAX_RESULTS, DEFAULT_MAX_RESULTS)
        )
        await async_send_charge_notification(
            self.hass,
            self._entry,
            self.coordinator.data,
            language=language,
            max_results=max_results,
        )
