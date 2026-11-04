"""Find Yealink phones in the local network.

The phone's web interface answers on HTTPS with a page whose title contains
the model name (``Yealink T54W Phone``).  That makes a plain TCP/TLS probe a
cheap and reliable fingerprint, without needing credentials.

This module only uses the standard library so it can be tested outside Home
Assistant as well.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import ssl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable

PROBE_TIMEOUT = 0.6
MAX_WORKERS = 96

_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.IGNORECASE)
_PHONE_SUFFIX_RE = re.compile(r"\s+phone$", re.IGNORECASE)


@dataclass(frozen=True)
class DiscoveredPhone:
    """A phone found by the network scan."""

    host: str
    model: str


def _probe(host: str, timeout: float = PROBE_TIMEOUT) -> DiscoveredPhone | None:
    """Return the phone at ``host`` or ``None`` when it is not a Yealink."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    connection = http.client.HTTPSConnection(
        host, 443, timeout=timeout, context=context
    )
    try:
        connection.request(
            "GET",
            "/",
            headers={"Connection": "close", "User-Agent": "HomeAssistant"},
        )
        response = connection.getresponse()
        body = response.read(16384).decode("utf-8", "replace")
    except (OSError, http.client.HTTPException, ssl.SSLError):
        return None
    finally:
        try:
            connection.close()
        except OSError:
            pass

    if "yealink" not in body.lower():
        return None

    match = _TITLE_RE.search(body)
    model = match.group(1).strip() if match else "Yealink"
    model = _PHONE_SUFFIX_RE.sub("", model) or "Yealink"
    return DiscoveredPhone(host=host, model=model)


def scan_networks(
    networks: Iterable[ipaddress.IPv4Network],
    *,
    timeout: float = PROBE_TIMEOUT,
    max_workers: int = MAX_WORKERS,
) -> list[DiscoveredPhone]:
    """Probe every host in ``networks`` and return the Yealink phones found."""
    hosts: list[str] = []
    for network in networks:
        hosts.extend(str(host) for host in network.hosts())
    # Deduplicate while keeping a stable order (overlapping networks).
    hosts = list(dict.fromkeys(hosts))
    if not hosts:
        return []

    workers = min(max_workers, len(hosts))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda host: _probe(host, timeout), hosts))

    phones = [phone for phone in results if phone is not None]
    return sorted(phones, key=lambda phone: ipaddress.ip_address(phone.host))
