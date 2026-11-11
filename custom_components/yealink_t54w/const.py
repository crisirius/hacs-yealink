"""Constants for the Yealink T5x integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

DOMAIN: Final = "yealink_t54w"

MANUFACTURER: Final = "Yealink"

CONF_HOST: Final = "host"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_VERIFY_TLS: Final = "verify_tls"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_ENABLE_CALL_CONTROL: Final = "enable_call_control"
CONF_ENABLE_HEADSET: Final = "enable_headset"
CONF_SYSLOG_PORT: Final = "syslog_port"
CONF_CONFIGURE_SYSLOG: Final = "configure_syslog"

DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_SYSLOG_PORT: Final = 5514
DEFAULT_VERIFY_TLS: Final = False

MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600
MIN_SYSLOG_PORT: Final = 1024
MAX_SYSLOG_PORT: Final = 65535

ACCOUNT_REFRESH: Final = 60
CALLLOG_REFRESH: Final = 60
HEADSET_REFRESH: Final = 60
CALLLOG_LIMIT: Final = 20

ACCOUNT_STATUS: Final[dict[str, str]] = {
    "0": "Disabled",
    "1": "Registering",
    "2": "Registered",
    "3": "Register Failed",
    "6": "Inexistence",
}

CALL_TYPES: Final[dict[str, str]] = {
    "0": "All",
    "1": "Dialed",
    "2": "Received",
    "3": "Missed",
    "4": "Forwarded",
}

ATTR_ENTRY_ID: Final = "entry_id"

_MAC_SEPARATORS = str.maketrans("", "", ":-. \t\r\n")
_HEX_DIGITS = frozenset("0123456789abcdef")


def call_control_enabled(options: Mapping[str, Any]) -> bool:
    """Return whether dial and hangup features are enabled for an entry."""
    return bool(options.get(CONF_ENABLE_CALL_CONTROL, True))


def as_int(value: Any, default: int = 0) -> int:
    """Convert ``value`` to int, falling back when the phone sends junk."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_mac(value: str) -> str:
    """Return a MAC address as lowercase hex without separators."""
    return value.translate(_MAC_SEPARATORS).lower()


def is_mac(value: str) -> bool:
    """Return True when ``value`` looks like a 48-bit MAC address."""
    normalized = normalize_mac(value)
    return len(normalized) == 12 and all(char in _HEX_DIGITS for char in normalized)


def format_mac(value: str) -> str:
    """Return a colon-separated MAC address, or an empty string."""
    normalized = normalize_mac(value)
    if not is_mac(normalized):
        return ""
    return ":".join(normalized[index : index + 2] for index in range(0, 12, 2))


def resolve_unique_id(
    info_mac: str, dhcp_mac: str | None, host: str
) -> str:
    """Pick the most stable unique ID available for a config entry."""
    normalized = normalize_mac(info_mac)
    if is_mac(normalized):
        return normalized
    if dhcp_mac:
        normalized_dhcp = normalize_mac(dhcp_mac)
        if is_mac(normalized_dhcp):
            return normalized_dhcp
    return host.lower()


def trans_account_status(code: Any) -> str:
    """Mirror the web UI's ``transAccountStatus()``."""
    code = str(code)
    if code in {"-1", "4", "7", "8", "9", "10"}:
        code = "1"
    elif code in {"5", "11"}:
        code = "2"
    return ACCOUNT_STATUS.get(code, "Unknown")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "on", "yes"}


def pick(data: dict, prefix: str) -> dict:
    return {
        key[len(prefix) :]: value
        for key, value in data.items()
        if key.startswith(prefix)
    }
