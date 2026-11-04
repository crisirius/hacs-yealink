"""Sensor platform for the Yealink T5x integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .coordinator import PhoneData, YealinkCoordinator
from .entity import YealinkEntity


@dataclass(frozen=True, kw_only=True)
class YealinkSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[PhoneData], StateType | datetime]


SENSORS: tuple[YealinkSensorDescription, ...] = (
    YealinkSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "in_call"],
        icon="mdi:phone",
        value_fn=lambda data: data.call_state,
    ),
    YealinkSensorDescription(
        key="firmware",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.phone.get("firmware") or None,
    ),
    YealinkSensorDescription(
        key="ip_address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.phone.get("ip") or None,
    ),
    YealinkSensorDescription(
        key="wifi_ssid",
        icon="mdi:wifi",
        value_fn=lambda data: data.wifi.get("ssid") or None,
    ),
    YealinkSensorDescription(
        key="wifi_signal",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi-strength-2",
        value_fn=lambda data: data.wifi.get("signal_percent"),
    ),
    YealinkSensorDescription(
        key="last_poll",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.polled_at,
    ),
)

HEADSET_NAME = YealinkSensorDescription(
    key="headset_name",
    icon="mdi:headset",
    value_fn=lambda data: (data.headset or {}).get("name") or None,
)

HEADSET_MAC = YealinkSensorDescription(
    key="headset_mac",
    icon="mdi:bluetooth",
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda data: (data.headset or {}).get("mac") or None,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator: YealinkCoordinator = runtime.coordinator

    entities: list[SensorEntity] = [
        YealinkSensor(coordinator, entry, description) for description in SENSORS
    ]
    entities.append(LastCallSensor(coordinator, entry))

    for account in coordinator.data.accounts:
        entities.append(AccountStatusSensor(coordinator, entry, account))
        entities.append(AccountNumberSensor(coordinator, entry, account))

    if runtime.syslog is not None:
        entities.append(YealinkSensor(coordinator, entry, HEADSET_NAME))
        entities.append(YealinkSensor(coordinator, entry, HEADSET_MAC))

    async_add_entities(entities)


class YealinkSensor(YealinkEntity, SensorEntity):
    """Generic sensor driven by a description."""

    entity_description: YealinkSensorDescription

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        description: YealinkSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)


class LastCallSensor(YealinkEntity, SensorEntity):
    """Show the most recent call from the phone's call log."""

    _attr_translation_key = "last_call"
    _attr_icon = "mdi:phone-log"

    def __init__(self, coordinator: YealinkCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "last_call")

    @property
    def native_value(self) -> StateType:
        call = self.coordinator.data.last_call
        if not call:
            return None
        return call.get("name") or call.get("number") or None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        call = self.coordinator.data.last_call
        if not call:
            return None
        return {
            "direction": call.get("direction"),
            "number": call.get("number"),
            "time": call.get("time"),
            "duration": call.get("duration"),
            "local": call.get("local"),
            "local_server": call.get("local_server"),
        }


class _AccountSensor(YealinkEntity, SensorEntity):
    """Base class for per-account sensors."""

    _attr_icon = "mdi:account-voice"

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        account: dict[str, Any],
        key: str,
    ) -> None:
        super().__init__(coordinator, entry, key)
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


class AccountStatusSensor(_AccountSensor):
    """Registration status of one account."""

    _attr_translation_key = "account_status"

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        account: dict[str, Any],
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            account,
            f"account_{account.get('id')}_status",
        )

    @property
    def native_value(self) -> StateType:
        account = self._account
        return account.get("status_text") if account else None


class AccountNumberSensor(_AccountSensor):
    """Phone number of one account."""

    _attr_translation_key = "account_number"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: YealinkCoordinator,
        entry: ConfigEntry,
        account: dict[str, Any],
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            account,
            f"account_{account.get('id')}_number",
        )

    @property
    def native_value(self) -> StateType:
        account = self._account
        return account.get("number") if account else None
