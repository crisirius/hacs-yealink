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
    """Receive UDP syslog messages and extract the Bluetooth headset state."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self._lock = threading.Lock()
        self._seq = 0
        self._headset: dict[str, Any] | None = None
        self._headset_seq = 0
        self.message_count = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
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


async def async_start_syslog(
    hass: HomeAssistant, port: int
) -> tuple[SyslogReceiver | None, asyncio.DatagramTransport | None]:
    """Bind the syslog UDP port.  Returns ``(None, None)`` when unavailable."""
    receiver = SyslogReceiver()
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
