"""Minimal syslog receiver used for Bluetooth headset detection.

The Yealink web API does not expose the connected Bluetooth headset.  Asking
the phone for its dongle status makes it emit a syslog line such as::

    control bt dongle[1][Yealink T54W][...] dev[Jabra Evolve 65 SE][50:...] connect[1]

This module listens for those lines.  It intentionally keeps no log buffer;
only the most recent headset state is stored.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_BT_DEVICE = re.compile(
    r"control bt dongle\[(?P<dongle>[^\]]*)\]\[(?P<adapter>[^\]]*)\].*?"
    r"dev\[(?P<name>[^\]]*)\]\[(?P<mac>[^\]]*)\].*?"
    r"connect\[(?P<connect>[^\]]*)\]"
)


class SyslogReceiver(asyncio.DatagramProtocol):
    """Receive UDP syslog messages and extract the Bluetooth headset state.

    Only datagrams from the configured phone address are accepted, so other
    hosts cannot inject a fake headset state.
    """

    def __init__(self, phone_ip: str | None = None) -> None:
        self.phone_ip = phone_ip
        self.transport: asyncio.DatagramTransport | None = None
        self._lock = threading.Lock()
        self._seq = 0
        self._headset: dict[str, Any] | None = None
        self._headset_seq = 0
        self.message_count = 0
        self.ignored_count = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.phone_ip and addr[0] != self.phone_ip:
            self.ignored_count += 1
            return
        text = data.decode("utf-8", "replace").rstrip("\x00\r\n")
        match = _BT_DEVICE.search(text)
        with self._lock:
            self._seq += 1
            self.message_count += 1
            if match:
                self._headset = {
                    "connected": match.group("connect").strip() == "1",
                    "name": match.group("name").strip(),
                    "mac": match.group("mac").strip(),
                    "type": "Bluetooth",
                }
                self._headset_seq = self._seq

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def headset_state(self, after: int | None = None) -> dict[str, Any] | None:
        """Return the last headset state, optionally only if newer than ``after``."""
        with self._lock:
            if self._headset is None:
                return None
            if after is not None and self._headset_seq <= after:
                return None
            return dict(self._headset)


async def _async_resolve(hass: HomeAssistant, host: str | None) -> str | None:
    """Resolve the configured phone address to an IPv4 address."""
    if not host:
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        return host
    try:
        return await hass.async_add_executor_job(socket.gethostbyname, host)
    except OSError:
        _LOGGER.debug("Could not resolve %s for syslog filtering", host)
        return None


async def async_start_syslog(
    hass: HomeAssistant, port: int, host: str | None = None
) -> tuple[SyslogReceiver | None, asyncio.DatagramTransport | None]:
    """Bind the syslog UDP port.  Returns ``(None, None)`` when unavailable."""
    receiver = SyslogReceiver(await _async_resolve(hass, host))
    try:
        transport, _ = await hass.loop.create_datagram_endpoint(
            lambda: receiver, local_addr=("0.0.0.0", port)
        )
    except OSError as exc:
        _LOGGER.warning(
            "Could not bind UDP port %s for headset detection: %s. "
            "Headset entities will be unavailable.",
            port,
            exc,
        )
        return None, None
    _LOGGER.debug("Listening for Yealink syslog on UDP %s", port)
    return receiver, transport  # type: ignore[return-value]
