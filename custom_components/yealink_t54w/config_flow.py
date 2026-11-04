"""Config and options flow for the Yealink T5x integration."""

from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

try:  # Home Assistant 2024.x
    from homeassistant.components.dhcp import DhcpServiceInfo
except ImportError:  # Home Assistant 2025.x and newer
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

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
from .discovery import DiscoveredPhone, scan_networks

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

MAX_SCAN_NETWORKS = 4

# Interfaces that normally do not lead to a phone on the LAN.
_VIRTUAL_ADAPTER_TOKENS = (
    "docker",
    "veth",
    "virbr",
    "br-",
    "vmnet",
    "vboxnet",
    "utun",
    "tap",
    "tun",
    "bridge",
)


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


def _phone_selector(phones: list[DiscoveredPhone]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                str(phone.host) for phone in sorted(phones, key=lambda p: p.host)
            ],
            mode=SelectSelectorMode.LIST,
        )
    )


def _normalize_host(value: str) -> str:
    """Accept ``172.20.1.130``, ``https://phone/`` and similar input."""
    host = value.strip()
    if "://" in host:
        parsed = urllib.parse.urlsplit(host)
        host = parsed.hostname or host
        try:
            if parsed.port:
                host = f"{host}:{parsed.port}"
        except ValueError:
            pass
    return host.rstrip("/")


def _settings_schema(
    *, include_host: bool = False, defaults: dict[str, Any] | None = None
) -> vol.Schema:
    """Build the form with the connection and polling settings."""
    defaults = defaults or {}
    fields: dict[Any, Any] = {}

    if include_host:
        fields[
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, ""))
        ] = cv.string
    fields[
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin"))
    ] = cv.string
    fields[vol.Required(CONF_PASSWORD)] = PASSWORD_SELECTOR
    fields[
        vol.Optional(
            CONF_VERIFY_TLS,
            default=defaults.get(CONF_VERIFY_TLS, DEFAULT_VERIFY_TLS),
        )
    ] = cv.boolean
    fields[
        vol.Optional(
            CONF_SCAN_INTERVAL,
            default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
    ] = _scan_interval_selector()
    fields[
        vol.Optional(
            CONF_ENABLE_CALL_CONTROL,
            default=defaults.get(CONF_ENABLE_CALL_CONTROL, True),
        )
    ] = cv.boolean
    fields[
        vol.Optional(
            CONF_ENABLE_HEADSET,
            default=defaults.get(CONF_ENABLE_HEADSET, True),
        )
    ] = cv.boolean
    fields[
        vol.Optional(
            CONF_SYSLOG_PORT,
            default=defaults.get(CONF_SYSLOG_PORT, DEFAULT_SYSLOG_PORT),
        )
    ] = _port_selector()
    fields[
        vol.Optional(
            CONF_CONFIGURE_SYSLOG,
            default=defaults.get(CONF_CONFIGURE_SYSLOG, True),
        )
    ] = cv.boolean

    return vol.Schema(fields)


def _is_virtual_adapter(name: str) -> bool:
    lowered = name.lower()
    # Loopback is called ``lo`` on Linux and ``lo0`` on macOS.  Do not use a
    # plain substring match here, otherwise Wi-Fi names such as ``wlo1`` would
    # be skipped as well.
    if lowered == "lo" or (
        lowered.startswith("lo") and lowered[2:].isdigit()
    ):
        return True
    return any(token in lowered for token in _VIRTUAL_ADAPTER_TOKENS)


def _networks_from_address(
    address: str, prefix: int | None
) -> list[ipaddress.IPv4Network]:
    """Return the /24 networks worth scanning for one interface address."""
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return []

    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or not ip.is_private
    ):
        return []

    if prefix is None or not 0 <= prefix <= 32:
        prefix = 24

    if prefix < 24:
        if (1 << (24 - prefix)) > MAX_SCAN_NETWORKS:
            return [ipaddress.IPv4Network(f"{ip}/24", strict=False)]
        network = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
        return list(network.subnets(new_prefix=24))

    return [ipaddress.IPv4Network(f"{ip}/24", strict=False)]


def _netmask_to_prefix(netmask: str | None) -> int | None:
    if not netmask:
        return None
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
    except ValueError:
        return None


def _default_route_network() -> list[ipaddress.IPv4Network]:
    """Best-effort fallback when no adapter information is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # A UDP connect does not send packets, it only selects a route.
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
    except OSError:
        return []
    return _networks_from_address(address, 24)


def _fallback_networks() -> list[ipaddress.IPv4Network]:
    """Read the interfaces with psutil when the network integration is absent."""
    try:
        import psutil
    except ImportError:
        return _default_route_network()

    try:
        addresses = psutil.net_if_addrs()
    except Exception:  # noqa: BLE001 - optional dependency
        return _default_route_network()

    networks: list[ipaddress.IPv4Network] = []
    for name, entries in addresses.items():
        if _is_virtual_adapter(name):
            continue
        for entry in entries:
            if entry.family != socket.AF_INET:
                continue
            prefix = _netmask_to_prefix(entry.netmask)
            networks.extend(_networks_from_address(entry.address, prefix))

    return networks or _default_route_network()


async def _async_local_networks(
    hass: HomeAssistant,
) -> list[ipaddress.IPv4Network]:
    """Return up to four private /24 networks to probe."""
    adapters: list[Any] = []
    try:
        from homeassistant.components.network import async_get_adapters

        adapters = await async_get_adapters(hass)
    except Exception:  # noqa: BLE001 - the network integration is optional
        _LOGGER.debug("Could not read the network adapters", exc_info=True)

    networks: list[ipaddress.IPv4Network] = []
    for adapter in adapters:
        if not adapter.get("enabled", True):
            continue
        if _is_virtual_adapter(str(adapter.get("name") or "")):
            continue
        for ipv4 in adapter.get("ipv4") or []:
            networks.extend(
                _networks_from_address(
                    str(ipv4.get("address") or ""),
                    ipv4.get("network_prefix"),
                )
            )

    if not networks:
        networks = await hass.async_add_executor_job(_fallback_networks)

    unique: list[ipaddress.IPv4Network] = []
    for network in networks:
        if network not in unique:
            unique.append(network)
    return unique[:MAX_SCAN_NETWORKS]


class YealinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._discovered: list[DiscoveredPhone] = []
        self._host: str | None = None
        self._model: str | None = None
        self._dhcp_mac: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user",
            menu_options=["manual", "scan"],
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._async_validate_and_create(
                host=_normalize_host(str(user_input[CONF_HOST])),
                user_input=user_input,
                step_id="manual",
                include_host=True,
            )

        return self.async_show_form(
            step_id="manual",
            data_schema=_settings_schema(include_host=True),
        )

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            host = str(user_input[CONF_HOST])
            phone = next(
                (item for item in self._discovered if item.host == host), None
            )
            self._host = host
            self._model = phone.model if phone else None
            return await self.async_step_credentials()

        networks = await _async_local_networks(self.hass)
        if not networks:
            return self.async_abort(reason="no_network")

        try:
            phones = await self.hass.async_add_executor_job(scan_networks, networks)
        except Exception:  # noqa: BLE001 - report a clean abort to the user
            _LOGGER.exception("The Yealink network scan failed")
            return self.async_abort(reason="scan_failed")

        if not phones:
            return self.async_abort(reason="no_devices_found")

        self._discovered = phones
        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST): _phone_selector(phones)}
            ),
            description_placeholders={"count": str(len(phones))},
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a phone announced by the DHCP integration."""
        host = discovery_info.ip
        mac = (
            discovery_info.macaddress.replace(":", "").replace("-", "").lower()
        )
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self.context["title_placeholders"] = {"name": host}
        self._host = host
        self._model = None
        self._dhcp_mac = mac
        return await self.async_step_credentials()

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._host is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            return await self._async_validate_and_create(
                host=self._host,
                user_input=user_input,
                step_id="credentials",
                include_host=False,
            )

        return self.async_show_form(
            step_id="credentials",
            data_schema=_settings_schema(),
            description_placeholders=self._placeholders(),
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

    def _placeholders(self) -> dict[str, str]:
        return {
            "host": self._host or "",
            "model": self._model or "Yealink",
        }

    async def _async_validate_and_create(
        self,
        *,
        host: str,
        user_input: dict[str, Any],
        step_id: str,
        include_host: bool,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
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
            await self.async_set_unique_id(
                mac or self._dhcp_mac or self._host or host.lower()
            )
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

            model = info.get("wui.device.phoneName") or self._model or "Yealink"
            title = model if model.lower().startswith("yealink") else f"Yealink {model}"

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
            step_id=step_id,
            data_schema=_settings_schema(
                include_host=include_host, defaults=user_input
            ),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

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

        # ``OptionsFlow.config_entry`` only exists in newer Home Assistant
        # versions; fall back to the flow handler for 2024.11.
        entry = getattr(self, "config_entry", None)
        if entry is None:
            entry = self.hass.config_entries.async_get_entry(self.handler)
        options = entry.options if entry is not None else {}
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
