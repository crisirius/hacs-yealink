"""Tests for the vendored Yealink API client."""

from __future__ import annotations

import pytest
from component_loader import load_module

api = load_module("api")


class _FakeResponse:
    def __init__(self, body: bytes = b'{"ret":"ok","data":{}}') -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _RecordingOpener:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def open(self, request: object, timeout: float | None = None) -> _FakeResponse:
        self.requests.append(request)
        return _FakeResponse()


@pytest.mark.parametrize("method", ["reboot", "restart_web", "logout"])
def test_bodyless_post_commands_send_an_empty_json_body(method: str) -> None:
    client = api.Yealink("phone")
    opener = _RecordingOpener()
    client._opener = opener

    getattr(client, method)()

    request = opener.requests[0]
    assert request.data == b"{}"  # type: ignore[attr-defined]


def test_post_commands_send_the_csrf_token() -> None:
    client = api.Yealink("phone")
    client.csrf_token = "token"
    opener = _RecordingOpener()
    client._opener = opener

    client.reboot()

    request = opener.requests[0]
    assert request.get_header("X-csrftoken") == "token"  # type: ignore[attr-defined]


def test_rsa_key_handles_non_dict_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = api.Yealink("phone")

    def fail(*args: object, **kwargs: object) -> None:
        raise api.YealinkError("failed", error="not a dict")

    monkeypatch.setattr(client, "post", fail)

    with pytest.raises(api.YealinkError, match="could not obtain RSA public key"):
        client.rsa_key()


def test_is_auth_error_detects_expired_session() -> None:
    error = api.YealinkError("failed", error={"webStatus": "noauth"})
    assert api.is_auth_error(error)


def test_is_auth_error_ignores_other_errors() -> None:
    assert not api.is_auth_error(api.YealinkError("failed", error={}))


def test_is_wrong_password_detects_rejection() -> None:
    error = api.YealinkError("failed", error={"msg": "Wrong password"})
    assert api.is_wrong_password(error)


def test_is_wrong_password_ignores_other_errors() -> None:
    assert not api.is_wrong_password(api.YealinkError("failed", error={"msg": "no"}))
