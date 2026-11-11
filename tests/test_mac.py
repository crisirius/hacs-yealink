"""Tests for MAC address helpers."""

from __future__ import annotations

from component_loader import load_module

const = load_module("const")
format_mac = const.format_mac
is_mac = const.is_mac
normalize_mac = const.normalize_mac


def test_normalize_mac_strips_colons() -> None:
    assert normalize_mac("80:5E:0C:12:34:56") == "805e0c123456"


def test_normalize_mac_strips_hyphens() -> None:
    assert normalize_mac("80-5E-0C-12-34-56") == "805e0c123456"


def test_normalize_mac_strips_dots() -> None:
    assert normalize_mac("805E.C123.4567") == "805ec1234567"


def test_normalize_mac_strips_whitespace() -> None:
    assert normalize_mac("  80 5E 0C 12 34 56  ") == "805e0c123456"


def test_normalize_mac_keeps_existing_form() -> None:
    assert normalize_mac("805E0C123456") == "805e0c123456"


def test_normalize_mac_empty() -> None:
    assert normalize_mac("") == ""


def test_is_mac_accepts_all_common_formats() -> None:
    assert is_mac("805e0c123456")
    assert is_mac("80:5E:0C:12:34:56")
    assert is_mac("80-5E-0C-12-34-56")


def test_is_mac_rejects_hostnames_and_ip_addresses() -> None:
    assert not is_mac("192.168.1.10")
    assert not is_mac("PHONE_HOST")
    assert not is_mac("")


def test_is_mac_rejects_invalid_hex() -> None:
    assert not is_mac("805e0c12345g")


def test_format_mac_returns_colon_form() -> None:
    assert format_mac("805E0C123456") == "80:5e:0c:12:34:56"
    assert format_mac("80:5E:0C:12:34:56") == "80:5e:0c:12:34:56"


def test_format_mac_returns_empty_for_non_mac() -> None:
    assert format_mac("PHONE_HOST") == ""
