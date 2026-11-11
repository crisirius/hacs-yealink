"""Tests for manifest invariants that Home Assistant does not validate."""

from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST = (
    Path(__file__).parents[1]
    / "custom_components"
    / "yealink_t54w"
    / "manifest.json"
)

# Home Assistant indexes DHCP matchers by the first six characters of the
# manifest value and looks them up with the first six characters of the
# uppercase, separator-free MAC address.  Anything else never matches.
_DHCP_MAC_RE = re.compile(r"[0-9A-F]{6}\*")


def test_dhcp_mac_matchers_are_compatible_with_home_assistant() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for matcher in manifest["dhcp"]:
        mac = matcher.get("macaddress")
        if mac is None:
            continue
        assert _DHCP_MAC_RE.fullmatch(mac), (
            f"DHCP matcher {mac!r} cannot match: use six hex characters "
            "without separators followed by '*'"
        )


def test_dhcp_matcher_keys_equal_the_home_assistant_lookup_key() -> None:
    """Reproduce the lookup HA performs for a real DHCP lease.

    Home Assistant indexes matchers by ``macaddress[:6]`` and looks them up
    with the first six characters of the uppercase, separator-free MAC.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for matcher in manifest["dhcp"]:
        mac = matcher.get("macaddress")
        if mac is None:
            continue
        oui = mac[:6]
        sample_mac = ":".join(
            [oui[index : index + 2] for index in range(0, 6, 2)]
            + ["12", "34", "56"]
        )
        lookup_key = sample_mac.replace(":", "").upper()[:6]
        assert lookup_key == oui
