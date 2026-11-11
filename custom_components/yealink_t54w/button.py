"""Button platform for the Yealink T5x integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import YealinkError
from .const import DOMAIN, call_control_enabled
from .coordinator import YealinkCoordinator
from .entity import YealinkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: YealinkCoordinator = runtime.coordinator
    entities: list[ButtonEntity] = [RebootButton(coordinator, entry)]
    if call_control_enabled(entry.options):
        entities.insert(0, HangupButton(coordinator, entry))
    async_add_entities(entities)


class _PhoneButton(YealinkEntity, ButtonEntity):
    """Base class for buttons that call the phone API."""

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator, entry, key)
        self._attr_translation_key = key

    async def _run(self, action: str) -> None:
        try:
            await self.hass.async_add_executor_job(
                getattr(self.coordinator.client, action)
            )
        except YealinkError as exc:
            raise HomeAssistantError(f"Phone command {action} failed: {exc}") from exc
        await self.coordinator.async_request_refresh()


class HangupButton(_PhoneButton):
    """Hang up the current call."""

    _attr_icon = "mdi:phone-hangup"

    def __init__(self, coordinator: YealinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "hangup")

    async def async_press(self) -> None:
        await self._run("hangup")


class RebootButton(_PhoneButton):
    """Reboot the phone.

    Disabled by default: a single mis-tap would drop the phone for a minute.
    """

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: YealinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "reboot")

    async def async_press(self) -> None:
        await self._run("reboot")
