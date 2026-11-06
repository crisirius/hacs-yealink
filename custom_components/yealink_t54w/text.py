"""Text platform for the Yealink T5x integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import YealinkError
from .const import DOMAIN
from .coordinator import YealinkCoordinator
from .entity import YealinkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the dial text entity for this phone."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: YealinkCoordinator = runtime.coordinator
    async_add_entities([YealinkDialTextEntity(coordinator, entry)])


class YealinkDialTextEntity(YealinkEntity, TextEntity):
    """Text holding a phone number to dial on the phone."""

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "dial_number")
        self._attr_native_value = None
        self._attr_mode = TextMode.TEXT

    @property
    def native_value(self) -> str | None:
        runtime: Any = (
            self.coordinator.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        )
        value = (runtime.dial_number or "").strip()
        return value or None

    async def async_set_value(self, value: str) -> None:
        """Set the number to dial and place the call."""
        number = (value or "").strip()
        if not number:
            raise HomeAssistantError("The dial number must not be empty")
        runtime: Any = (
            self.coordinator.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        )
        runtime.dial_number = number
        try:
            await self.hass.async_add_executor_job(runtime.client.dial, number, "Auto")
        except YealinkError as exc:
            raise HomeAssistantError(f"Phone dial failed: {exc}") from exc
        await runtime.coordinator.async_request_refresh()
