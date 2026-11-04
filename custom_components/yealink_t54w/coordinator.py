"""Data update coordinator for the Yealink T5x integration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Yealink, YealinkError, is_auth_error, is_wrong_password
from .const import (
    ACCOUNT_REFRESH,
    CALL_TYPES,
    CALLLOG_LIMIT,
    CALLLOG_REFRESH,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    HEADSET_REFRESH,
    as_bool,
    pick,
    trans_account_status,
)
from .syslog import SyslogReceiver

_LOGGER = logging.getLogger(__name__)


@dataclass
class PhoneData:
    """Snapshot of the phone state."""

    online: bool
    talking: bool
    call_state: str
    phone: dict[str, Any]
    accounts: list[dict[str, Any]]
    wifi: dict[str, Any]
    headset: dict[str, Any] | None
    last_call: dict[str, Any] | None
    polled_at: datetime
    poll_count: int


class YealinkCoordinator(DataUpdateCoordinator[PhoneData]):
    """Poll the phone and translate the raw API into a small snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: Yealink,
        syslog: SyslogReceiver | None,
    ) -> None:
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"Yealink {entry.title}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.syslog = syslog

        self._account_cache: list[dict[str, Any]] = []
        self._account_time = 0.0
        self._calls: list[dict[str, Any]] = []
        self._calllog_time = 0.0
        self._headset_cache: dict[str, Any] | None = None
        self._headset_time = 0.0
        self._poll_count = 0

    # ------------------------------------------------------------------ update

    async def _async_update_data(self) -> PhoneData:
        try:
            return await self.hass.async_add_executor_job(self._fetch)
        except ConfigEntryAuthFailed:
            raise
        except YealinkError as exc:
            if is_wrong_password(exc):
                raise ConfigEntryAuthFailed(
                    "The phone rejected the stored credentials"
                ) from exc
            raise UpdateFailed(str(exc)) from exc
        except OSError as exc:
            raise UpdateFailed(f"transport error: {exc}") from exc

    def _fetch(self) -> PhoneData:
        try:
            return self._fetch_once()
        except YealinkError as exc:
            if not is_auth_error(exc):
                raise
            _LOGGER.info("Session expired, logging in again")
            self._relogin()
            return self._fetch_once()

    def _relogin(self) -> None:
        try:
            self.client.login()
        except YealinkError as exc:
            if is_wrong_password(exc):
                raise ConfigEntryAuthFailed(
                    "The phone rejected the stored credentials"
                ) from exc
            raise

    def _optional(self, func: Callable[[], Any], default: Any) -> Any:
        """Run an optional request; auth errors still abort the poll."""
        try:
            return func()
        except YealinkError as exc:
            if is_auth_error(exc):
                raise
            _LOGGER.debug("Optional phone request failed: %s", exc)
            return default

    def _fetch_once(self) -> PhoneData:
        now = time.time()

        info = self.client.info(["wui.device"])
        device = pick(info, "wui.device.")

        statuses = self._optional(self.client.account_status, {}) or {}
        if now - self._account_time > ACCOUNT_REFRESH:
            self._account_cache = self._optional(self.client.account_info, []) or []
            self._account_time = now

        accounts: list[dict[str, Any]] = []
        for account in self._account_cache:
            status = statuses.get(str(account.get("id")), account.get("status", "0"))
            text = trans_account_status(status)
            if not account.get("userName"):
                continue
            accounts.append(
                {
                    "id": account.get("id"),
                    "label": account.get("label") or account.get("displayName") or "",
                    "number": account.get("userName") or "",
                    "server": account.get("sipServer") or "",
                    "status": str(status),
                    "status_text": text,
                    "registered": text == "Registered",
                }
            )

        wifi_raw = self._optional(self.client.wifi_status, {}) or {}
        connected = str(wifi_raw.get("constatus")) == "1"
        signal = int(wifi_raw.get("signal") or 0)
        wifi = {
            "connected": connected,
            "ssid": (wifi_raw.get("ssid") or "") if connected else "",
            "signal": signal,
            "signal_percent": min(100, round(signal / 4 * 100)) if connected else None,
            "channel": wifi_raw.get("channel"),
            "speed": wifi_raw.get("speed"),
            "freq": wifi_raw.get("fre"),
            "mac": wifi_raw.get("mac") or "",
        }

        if now - self._calllog_time > CALLLOG_REFRESH:
            calllog = self._optional(self.client.calllog, {}) or {}
            calls = calllog.get("calls") or []
            self._calls = [self._parse_call(call) for call in calls[:CALLLOG_LIMIT]]
            self._calllog_time = now

        headset = self._collect_headset(now)
        talking = as_bool(device.get("bTalking", False))
        self._poll_count += 1

        return PhoneData(
            online=True,
            talking=talking,
            call_state="in_call" if talking else "idle",
            phone={
                "name": device.get("phoneName") or "Yealink",
                "firmware": device.get("firmware") or "",
                "hardware": device.get("hardware") or "",
                "mac": device.get("mac") or "",
                "ip": self.client.host,
            },
            accounts=accounts,
            wifi=wifi,
            headset=headset,
            last_call=self._calls[0] if self._calls else None,
            polled_at=datetime.now(timezone.utc),
            poll_count=self._poll_count,
        )

    # ----------------------------------------------------------------- headset

    def _collect_headset(self, now: float) -> dict[str, Any] | None:
        """Ask the phone for its dongle status and read the resulting syslog line."""
        if self.syslog is None:
            return None
        if self._headset_time and now - self._headset_time < HEADSET_REFRESH:
            return dict(self._headset_cache) if self._headset_cache else None

        before = self.syslog.last_seq
        self._optional(lambda: self.client.get("/api/common/donglestatus?type=2"), None)
        deadline = time.time() + 0.5
        headset = None
        while time.time() < deadline:
            headset = self.syslog.headset_state(after=before)
            if headset is not None:
                break
            time.sleep(0.05)
        if headset is None:
            headset = self.syslog.headset_state()

        self._headset_cache = headset
        self._headset_time = now
        return dict(headset) if headset else None

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _parse_call(call: dict[str, Any]) -> dict[str, Any]:
        # the API's remote_name is the number, remote_display the display name
        number = call.get("remote_name") or ""
        return {
            "direction": CALL_TYPES.get(str(call.get("type")), "Unknown"),
            "name": call.get("remote_display") or number,
            "number": number,
            "time": call.get("datetime") or "",
            "duration": call.get("duration") or "",
            "local": call.get("local_name") or "",
            "local_server": call.get("local_server") or "",
        }
