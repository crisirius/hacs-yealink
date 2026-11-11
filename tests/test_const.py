"""Tests for pure helpers in const.py."""

from __future__ import annotations

from component_loader import load_module

const = load_module("const")


def test_call_control_is_enabled_by_default() -> None:
    assert const.call_control_enabled({})


def test_call_control_can_be_enabled() -> None:
    assert const.call_control_enabled({"enable_call_control": True})


def test_call_control_can_be_disabled() -> None:
    assert not const.call_control_enabled({"enable_call_control": False})


def test_as_int_parses_numbers() -> None:
    assert const.as_int("42") == 42
    assert const.as_int(7) == 7


def test_as_int_falls_back_for_invalid_values() -> None:
    assert const.as_int(None) == 0
    assert const.as_int("") == 0
    assert const.as_int("n/a") == 0
    assert const.as_int("3.5") == 0


def test_as_int_uses_custom_default() -> None:
    assert const.as_int("n/a", default=-1) == -1


def test_resolve_unique_id_prefers_the_mac() -> None:
    assert (
        const.resolve_unique_id(
            "80:5E:0C:12:34:56", "aa:bb:cc:dd:ee:ff", "phone.local"
        )
        == "805e0c123456"
    )


def test_resolve_unique_id_falls_back_to_the_dhcp_mac() -> None:
    assert (
        const.resolve_unique_id("not-a-mac", "AA:BB:CC:DD:EE:FF", "phone.local")
        == "aabbccddeeff"
    )


def test_resolve_unique_id_falls_back_to_the_host() -> None:
    assert (
        const.resolve_unique_id("not-a-mac", "also:not:a:mac", "PHONE.local")
        == "phone.local"
    )
