"""Number platform for the Yealink T5x integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Add the dial number entity for this phone."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: YealinkCoordinator = runtime.coordinator
    async_add_entities([YealinkDialNumberEntity(coordinator, entry)])


class _PhoneNumberEntity(YealinkEntity, NumberEntity):
    """Base class for number entities that trigger a phone call."""

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator, entry, key)
        self._attr_translation_key = key
        self._attr_icon = "mdi:phone"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 99999999999999.0
        self._attr_native_step = 1.0
        self._attr_mode = NumberMode.BOX

    async def _run_dial(self, number: str, account: str = "Auto") -> None:
        runtime: Any = (
            self.coordinator.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        )
        try:
            await self.hass.async_add_executor_job(runtime.client.dial, number, account)
        except YealinkError as exc:
            raise HomeAssistantError(f"Phone dial failed: {exc}") from exc
        await runtime.coordinator.async_request_refresh()


class YealinkDialNumberEntity(_PhoneNumberEntity):
    """Number to dial on the phone."""

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry, "dial_number")

    @property
    def native_value(self) -> float | None:
        runtime: Any = (
            self.coordinator.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        )
        value = (runtime.dial_number or "").strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        number = str(int(round(value))) if float(value).is_integer() else str(value)
        number = number.strip()
        if not number:
            raise HomeAssistantError("The dial number must not be empty")
        runtime: Any = (
            self.coordinator.hass.data[DOMAIN][self.coordinator.config_entry.entry_id]
        )
        runtime.dial_number = number
        await self._run_dial(number)
