"""Binary sensor platform for the Yealink T5x integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import YealinkCoordinator
from .entity import YealinkEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: YealinkCoordinator = runtime.coordinator

    entities: list[BinarySensorEntity] = [
        OnlineBinarySensor(coordinator, entry),
        TalkingBinarySensor(coordinator, entry),
    ]
    for account in coordinator.data.accounts:
        entities.append(AccountRegisteredBinarySensor(coordinator, entry, account))

    if runtime.syslog is not None:
        entities.append(HeadsetConnectedBinarySensor(coordinator, entry))

    async_add_entities(entities)


class OnlineBinarySensor(YealinkEntity, BinarySensorEntity):
    """Whether the last poll of the phone succeeded."""

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: YealinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "online")

    @property
    def available(self) -> bool:
        # This sensor must stay available to report an outage.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class TalkingBinarySensor(YealinkEntity, BinarySensorEntity):
    """Whether the phone is currently in a call."""

    _attr_translation_key = "talking"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:phone-in-talk"

    def __init__(self, coordinator: YealinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "talking")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.talking


class AccountRegisteredBinarySensor(YealinkEntity, BinarySensorEntity):
    """Whether one SIP account is registered."""

    _attr_translation_key = "account_registered"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:account-check"

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        account: dict[str, Any],
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            f"account_{account.get('id')}_registered",
        )
        self._account_id = str(account.get("id"))
        self._attr_translation_placeholders = {
            "account": account.get("label") or f"Line {self._account_id}"
        }

    @property
    def _account(self) -> dict[str, Any] | None:
        for account in self.coordinator.data.accounts:
            if str(account.get("id")) == self._account_id:
                return account
        return None

    @property
    def available(self) -> bool:
        return super().available and self._account is not None

    @property
    def is_on(self) -> bool:
        account = self._account
        return bool(account and account.get("registered"))


class HeadsetConnectedBinarySensor(YealinkEntity, BinarySensorEntity):
    """Whether a Bluetooth headset is connected."""

    _attr_translation_key = "headset_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:headset"

    def __init__(self, coordinator: YealinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "headset_connected")

    @property
    def is_on(self) -> bool | None:
        headset = self.coordinator.data.headset
        if not headset:
            return None
        return bool(headset.get("connected"))
