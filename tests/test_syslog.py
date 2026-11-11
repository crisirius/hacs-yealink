"""Tests for the syslog headset parser."""

from __future__ import annotations

from component_loader import load_module

syslog = load_module("syslog")

HEADSET_LINE = (
    b"control bt dongle[1][Yealink T54W][...] "
    b"dev[Jabra Evolve 65 SE][50:AA:BB:CC:DD:EE] connect[1]"
)


def test_parses_connected_headset() -> None:
    receiver = syslog.SyslogReceiver(phone_ip="192.0.2.10")

    receiver.datagram_received(HEADSET_LINE, ("192.0.2.10", 5514))

    assert receiver.headset_state() == {
        "connected": True,
        "name": "Jabra Evolve 65 SE",
        "mac": "50:AA:BB:CC:DD:EE",
        "type": "Bluetooth",
    }


def test_ignores_packets_from_other_hosts() -> None:
    receiver = syslog.SyslogReceiver(phone_ip="192.0.2.10")

    receiver.datagram_received(HEADSET_LINE, ("192.0.2.99", 5514))

    assert receiver.headset_state() is None
    assert receiver.ignored_count == 1


def test_headset_state_can_be_filtered_by_sequence() -> None:
    receiver = syslog.SyslogReceiver(phone_ip="192.0.2.10")
    before = receiver.last_seq

    receiver.datagram_received(HEADSET_LINE, ("192.0.2.10", 5514))

    assert receiver.headset_state(after=before) is not None
    assert receiver.headset_state(after=receiver.last_seq) is None
