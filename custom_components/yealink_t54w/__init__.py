"""Yealink T5x phone integration for Home Assistant."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv

from .api import Yealink, YealinkError, is_wrong_password
from .const import (
    ATTR_ENTRY_ID,
    CONF_CONFIGURE_SYSLOG,
    CONF_ENABLE_CALL_CONTROL,
    CONF_ENABLE_HEADSET,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SYSLOG_PORT,
    CONF_USERNAME,
    CONF_VERIFY_TLS,
    DEFAULT_SYSLOG_PORT,
    DOMAIN,
)
from .coordinator import YealinkCoordinator
from .syslog import SyslogReceiver, async_start_syslog

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.TEXT,
]

SERVICE_DIAL = "dial"
SERVICE_HANGUP = "hangup"
SERVICE_REBOOT = "reboot"

SERVICE_DIAL_SCHEMA = vol.Schema(
    {
        vol.Required("number"): cv.string,
        vol.Optional("account", default="Auto"): cv.string,
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

SERVICE_TARGET_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


@dataclass
class YealinkRuntime:
    """Runtime objects for one configured phone."""

    entry: ConfigEntry
    client: Yealink
    coordinator: YealinkCoordinator
    syslog: SyslogReceiver | None
    previous_syslog: dict[str, str] | None
    dial_number: str = ""
    local_ip: str | None = None
    action_uri_added: bool = False


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the integration-wide services."""
    hass.data.setdefault(DOMAIN, {})
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one phone from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    host = entry.data[CONF_HOST]
    client = Yealink(
        host,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        verify_tls=bool(entry.data.get(CONF_VERIFY_TLS, False)),
        timeout=15.0,
    )

    try:
        await hass.async_add_executor_job(client.login)
        info = await hass.async_add_executor_job(client.info, ["wui.device"])
    except YealinkError as exc:
        if is_wrong_password(exc):
            raise ConfigEntryAuthFailed(
                "The phone rejected the configured credentials"
            ) from exc
        raise ConfigEntryNotReady(f"Could not connect to {host}: {exc}") from exc

    mac = (info.get("wui.device.mac") or "").lower()
    if mac and not entry.unique_id:
        hass.config_entries.async_update_entry(entry, unique_id=mac)

    options = entry.options
    syslog: SyslogReceiver | None = None
    previous_syslog: dict[str, str] | None = None

    if options.get(CONF_ENABLE_HEADSET, True):
        port = int(options.get(CONF_SYSLOG_PORT, DEFAULT_SYSLOG_PORT))
        syslog, _transport = await async_start_syslog(hass, port, host)
        if syslog is not None and options.get(CONF_CONFIGURE_SYSLOG, True):
            previous_syslog = await hass.async_add_executor_job(
                _configure_phone_syslog, client, host, port
            )

    action_uri_ip: str | None = None
    action_uri_added = False
    if options.get(CONF_ENABLE_CALL_CONTROL, True):
        action_uri_ip = await hass.async_add_executor_job(_local_ip, host)
        try:
            action_uri_added = await hass.async_add_executor_job(
                _ensure_action_uri, client, action_uri_ip
            )
            if action_uri_added:
                _LOGGER.info(
                    "Added Home Assistant to the phone's Action URI allow list"
                )
        except YealinkError as exc:
            _LOGGER.warning("Could not update the Action URI allow list: %s", exc)

    coordinator = YealinkCoordinator(hass, entry, client, syslog)
    try:
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        if syslog is not None:
            syslog.close()
        if action_uri_added and action_uri_ip:
            try:
                await hass.async_add_executor_job(
                    client.remove_action_uri_ip, action_uri_ip
                )
            except YealinkError as exc:
                _LOGGER.warning(
                    "Could not remove Home Assistant from the Action URI allow list: %s",
                    exc,
                )
        if previous_syslog:
            try:
                await hass.async_add_executor_job(
                    _restore_phone_syslog, client, previous_syslog
                )
            except YealinkError as exc:
                _LOGGER.warning("Could not restore the phone syslog settings: %s", exc)
        raise

    hass.data[DOMAIN][entry.entry_id] = YealinkRuntime(
        entry=entry,
        client=client,
        coordinator=coordinator,
        syslog=syslog,
        previous_syslog=previous_syslog,
        local_ip=action_uri_ip,
        action_uri_added=action_uri_added,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one phone."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    runtime: YealinkRuntime | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime is not None:
        if runtime.syslog is not None:
            runtime.syslog.close()
        if runtime.action_uri_added and runtime.local_ip:
            try:
                await hass.async_add_executor_job(
                    runtime.client.remove_action_uri_ip, runtime.local_ip
                )
            except YealinkError as exc:
                _LOGGER.warning(
                    "Could not remove Home Assistant from the Action URI allow list: %s",
                    exc,
                )
        if runtime.previous_syslog:
            try:
                await hass.async_add_executor_job(
                    _restore_phone_syslog,
                    runtime.client,
                    runtime.previous_syslog,
                )
            except YealinkError as exc:
                _LOGGER.warning("Could not restore the phone syslog settings: %s", exc)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


# --------------------------------------------------------------------------- services


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_DIAL):
        return

    async def handle_dial(call: ServiceCall) -> None:
        runtime = _runtime_for_call(hass, call)
        number = str(call.data["number"]).strip()
        if not number:
            raise HomeAssistantError("The dial number must not be empty")
        account = str(call.data.get("account") or "Auto")
        try:
            await hass.async_add_executor_job(runtime.client.dial, number, account)
        except YealinkError as exc:
            raise HomeAssistantError(f"Dial failed: {exc}") from exc
        await runtime.coordinator.async_request_refresh()

    async def handle_hangup(call: ServiceCall) -> None:
        runtime = _runtime_for_call(hass, call)
        try:
            await hass.async_add_executor_job(runtime.client.hangup)
        except YealinkError as exc:
            raise HomeAssistantError(f"Hangup failed: {exc}") from exc
        await runtime.coordinator.async_request_refresh()

    async def handle_reboot(call: ServiceCall) -> None:
        runtime = _runtime_for_call(hass, call)
        try:
            await hass.async_add_executor_job(runtime.client.reboot)
        except YealinkError as exc:
            raise HomeAssistantError(f"Reboot failed: {exc}") from exc

    hass.services.async_register(
        DOMAIN, SERVICE_DIAL, handle_dial, schema=SERVICE_DIAL_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_HANGUP, handle_hangup, schema=SERVICE_TARGET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT, handle_reboot, schema=SERVICE_TARGET_SCHEMA
    )


def _runtime_for_call(hass: HomeAssistant, call: ServiceCall) -> YealinkRuntime:
    runtimes: dict[str, YealinkRuntime] = hass.data.get(DOMAIN, {})
    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id:
        runtime = runtimes.get(entry_id)
        if runtime is None:
            raise HomeAssistantError(f"Unknown config entry: {entry_id}")
        return runtime
    if len(runtimes) == 1:
        return next(iter(runtimes.values()))
    if not runtimes:
        raise HomeAssistantError("No Yealink phone is configured")
    raise HomeAssistantError(
        "Multiple phones are configured; pass entry_id to select one"
    )


# ------------------------------------------------------------------- phone helpers


def _local_ip(host: str) -> str | None:
    """Return the local address this host uses to reach the phone."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, 443))
            return sock.getsockname()[0]
    except OSError:
        return None


def _ensure_action_uri(client: Yealink, ip: str | None) -> bool:
    if not ip:
        return False
    return client.ensure_action_uri_ip(ip)


def _configure_phone_syslog(
    client: Yealink, host: str, port: int
) -> dict[str, str] | None:
    """Point the phone's syslog at Home Assistant.

    Returns the previous values when something was changed, so they can be
    restored on unload.
    """
    ip = _local_ip(host)
    if not ip:
        _LOGGER.warning("Could not determine the local IP for syslog")
        return None

    wanted = {
        "SyslogSwitch": "1",
        "SyslogServerName": ip,
        "SyslogServerPort": str(port),
        "SyslogTransportType": "0",
    }
    try:
        current = client.read_config(list(wanted), page="SettingConfig")
    except YealinkError as exc:
        _LOGGER.warning("Could not read the phone syslog settings: %s", exc)
        return None

    previous = {key: str(current.get(key) or "") for key in wanted}
    if all(previous[key] == value for key, value in wanted.items()):
        return None

    try:
        client.write_config(wanted, page="SettingConfig")
    except YealinkError as exc:
        _LOGGER.warning("Could not update the phone syslog settings: %s", exc)
        return None

    _LOGGER.info("Pointed the phone syslog at %s:%s", ip, port)
    return previous


def _restore_phone_syslog(client: Yealink, previous: dict[str, str]) -> None:
    client.write_config(previous, page="SettingConfig")
