"""Constants for the Yealink T5x integration."""

from __future__ import annotations

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
