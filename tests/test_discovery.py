"""Tests for the network scan."""

from __future__ import annotations

import ipaddress
import ssl

import pytest
from component_loader import load_module

discovery = load_module("discovery")


def test_scan_networks_creates_one_ssl_context_per_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = 0
    real_create_default_context = ssl.create_default_context

    def counting_create_default_context() -> ssl.SSLContext:
        nonlocal created
        created += 1
        return real_create_default_context()

    monkeypatch.setattr(ssl, "create_default_context", counting_create_default_context)
    monkeypatch.setattr(
        discovery,
        "_probe",
        lambda host, timeout, context=None: None,
    )

    discovery.scan_networks([ipaddress.ip_network("192.0.2.0/30")])

    assert created == 1


def test_scan_networks_deduplicates_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_probe(host: str, timeout: float, context: ssl.SSLContext | None) -> object:
        if host in {"192.0.2.2", "192.0.2.1"}:
            return discovery.DiscoveredPhone(host=host, model="Yealink T54W")
        return None

    monkeypatch.setattr(discovery, "_probe", fake_probe)

    phones = discovery.scan_networks(
        [
            ipaddress.ip_network("192.0.2.0/30"),
            ipaddress.ip_network("192.0.2.0/30"),
        ]
    )

    assert [phone.host for phone in phones] == ["192.0.2.1", "192.0.2.2"]


def test_scan_networks_returns_empty_for_empty_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        discovery,
        "_probe",
        lambda host, timeout, context=None: pytest.fail("probe must not run"),
    )

    assert discovery.scan_networks([]) == []
