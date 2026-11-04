"""Base entity for the Yealink T5x integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, DOMAIN, MANUFACTURER
from .coordinator import YealinkCoordinator


class YealinkEntity(CoordinatorEntity[YealinkCoordinator]):
    """Base class that ties an entity to the phone device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        phone: dict[str, Any] = data.phone if data else {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.unique_id or self._entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=phone.get("name") or "T5x",
            name=self._entry.title,
            sw_version=phone.get("firmware") or None,
            hw_version=phone.get("hardware") or None,
            serial_number=phone.get("mac") or None,
            configuration_url=f"https://{self._entry.data[CONF_HOST]}",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
