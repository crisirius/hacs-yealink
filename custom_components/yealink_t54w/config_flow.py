"""Config and options flow for the Yealink T5x integration."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import Yealink, YealinkError, is_wrong_password
from .const import (
    CONF_CONFIGURE_SYSLOG,
    CONF_ENABLE_CALL_CONTROL,
    CONF_ENABLE_HEADSET,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SYSLOG_PORT,
    CONF_USERNAME,
    CONF_VERIFY_TLS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SYSLOG_PORT,
    DEFAULT_VERIFY_TLS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_SYSLOG_PORT,
    MIN_SCAN_INTERVAL,
    MIN_SYSLOG_PORT,
)

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _scan_interval_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL,
            max=MAX_SCAN_INTERVAL,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    )


def _port_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_SYSLOG_PORT,
            max=MAX_SYSLOG_PORT,
            step=1,
            mode=NumberSelectorMode.BOX,
        )
    )


def _normalize_host(value: str) -> str:
    """Accept ``172.20.1.130``, ``https://phone/`` and similar input."""
    host = value.strip()
    if "://" in host:
        host = urllib.parse.urlsplit(host).hostname or host
    return host.rstrip("/")


class YealinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(str(user_input[CONF_HOST]))
            try:
                info = await self._async_validate(
                    host,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_VERIFY_TLS],
                )
            except YealinkError as exc:
                errors["base"] = (
                    "invalid_auth" if is_wrong_password(exc) else "cannot_connect"
                )
            except Exception:  # noqa: BLE001 - show a generic error to the user
                _LOGGER.exception("Unexpected error while validating the phone")
                errors["base"] = "unknown"
            else:
                mac = (info.get("wui.device.mac") or "").lower()
                await self.async_set_unique_id(mac or host.lower())
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                model = info.get("wui.device.phoneName") or "Yealink"
                title = (
                    model if model.lower().startswith("yealink") else f"Yealink {model}"
                )

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_VERIFY_TLS: user_input[CONF_VERIFY_TLS],
                    },
                    options={
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        CONF_ENABLE_CALL_CONTROL: user_input[CONF_ENABLE_CALL_CONTROL],
                        CONF_ENABLE_HEADSET: user_input[CONF_ENABLE_HEADSET],
                        CONF_SYSLOG_PORT: user_input[CONF_SYSLOG_PORT],
                        CONF_CONFIGURE_SYSLOG: user_input[CONF_CONFIGURE_SYSLOG],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Required(CONF_USERNAME, default="admin"): cv.string,
                    vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                    vol.Optional(
                        CONF_VERIFY_TLS, default=DEFAULT_VERIFY_TLS
                    ): cv.boolean,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): _scan_interval_selector(),
                    vol.Optional(CONF_ENABLE_CALL_CONTROL, default=True): cv.boolean,
                    vol.Optional(CONF_ENABLE_HEADSET, default=True): cv.boolean,
                    vol.Optional(
                        CONF_SYSLOG_PORT, default=DEFAULT_SYSLOG_PORT
                    ): _port_selector(),
                    vol.Optional(CONF_CONFIGURE_SYSLOG, default=True): cv.boolean,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            try:
                await self._async_validate(
                    entry.data[CONF_HOST],
                    entry.data[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    entry.data.get(CONF_VERIFY_TLS, DEFAULT_VERIFY_TLS),
                )
            except YealinkError as exc:
                errors["base"] = (
                    "invalid_auth" if is_wrong_password(exc) else "cannot_connect"
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while validating the phone")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            errors=errors,
            description_placeholders={CONF_HOST: entry.data[CONF_HOST]},
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return YealinkOptionsFlow()

    async def _async_validate(
        self,
        host: str,
        username: str,
        password: str,
        verify_tls: bool,
    ) -> dict[str, Any]:
        def _validate() -> dict[str, Any]:
            client = Yealink(
                host,
                username,
                password,
                verify_tls=verify_tls,
                timeout=15.0,
            )
            client.login()
            return client.info(["wui.device"])

        return await self.hass.async_add_executor_job(_validate)


class YealinkOptionsFlow(OptionsFlow):
    """Options for an existing phone."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): _scan_interval_selector(),
                    vol.Optional(
                        CONF_ENABLE_CALL_CONTROL,
                        default=options.get(CONF_ENABLE_CALL_CONTROL, True),
                    ): cv.boolean,
                    vol.Optional(
                        CONF_ENABLE_HEADSET,
                        default=options.get(CONF_ENABLE_HEADSET, True),
                    ): cv.boolean,
                    vol.Optional(
                        CONF_SYSLOG_PORT,
                        default=options.get(CONF_SYSLOG_PORT, DEFAULT_SYSLOG_PORT),
                    ): _port_selector(),
                    vol.Optional(
                        CONF_CONFIGURE_SYSLOG,
                        default=options.get(CONF_CONFIGURE_SYSLOG, True),
                    ): cv.boolean,
                }
            ),
        )
