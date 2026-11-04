"""Minimal client for the Yealink T5x web API (T54W tested).

The phone's web UI is a Vue app that talks to a JSON API under ``/api/``.
Login passwords are RSA-encrypted client-side (PKCS#1 v1.5, hex, prefixed
with ``__WUI_ENC__:``).  This module reimplements that flow with the Python
standard library only, so the integration has no extra requirements.

This file is vendored from the standalone ``yealink`` toolset.  Keep the two
in sync when changing the protocol handling.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import random
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class YealinkError(RuntimeError):
    """Raised when the phone returns ``ret != ok`` or a transport error occurs."""

    def __init__(self, message: str, error: Any = None):
        super().__init__(message)
        self.error = error


def is_auth_error(exc: YealinkError) -> bool:
    """Return True when the phone reports an expired/invalid session."""
    return isinstance(exc.error, dict) and exc.error.get("webStatus") == "noauth"


def is_wrong_password(exc: YealinkError) -> bool:
    """Return True when the phone rejected the credentials themselves."""
    if not isinstance(exc.error, dict):
        return False
    message = " ".join(
        str(exc.error.get(key) or "") for key in ("msg", "ret", "error")
    ).lower()
    return "password" in message and ("wrong" in message or "invalid" in message)


def _rsa_encrypt(message: str, n_hex: str, e_hex: str) -> str:
    """PKCS#1 v1.5 encryption, matching the phone's bundled RSAKey.

    The firmware uses the raw RSAKey class (not the JSEncrypt wrapper), so
    ``encrypt()`` returns a hex string rather than base64.
    """
    n = int(n_hex, 16)
    e = int(e_hex, 16)
    k = (n.bit_length() + 7) // 8
    msg = message.encode("utf-8")
    ps_len = k - 3 - len(msg)
    if ps_len < 8:
        raise ValueError("message too long for RSA key")
    rng = random.SystemRandom()
    ps = bytes(rng.randrange(1, 256) for _ in range(ps_len))
    em = b"\x00\x02" + ps + b"\x00" + msg
    cipher = pow(int.from_bytes(em, "big"), e, n)
    return cipher.to_bytes(k, "big").hex()


class Yealink:
    def __init__(
        self,
        host: str,
        username: str | None = None,
        password: str | None = None,
        *,
        scheme: str = "https",
        timeout: float = 10.0,
        verify_tls: bool = False,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.base = f"{scheme}://{host}"
        self.timeout = timeout

        self.csrf_token: str | None = None
        self._jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        if not verify_tls:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(self._jar),
        )

    # ---------------------------------------------------------------- low level

    def _cookie(self, name: str) -> str | None:
        for cookie in self._jar:
            if cookie.name == name:
                return cookie.value
        return None

    def _request(
        self, method: str, path: str, data: Any = None, *, form: bool = False
    ) -> dict:
        url = path if path.startswith("http") else self.base + path
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}t={random.randrange(1 << 31)}"

        body = None
        headers = {"Accept": "application/json"}
        if data is not None:
            if form:
                if isinstance(data, dict):
                    body = urllib.parse.urlencode(data).encode()
                elif isinstance(data, str):
                    body = data.encode()
                else:
                    body = bytes(data)
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(data).encode()
                headers["Content-Type"] = "application/json;charset=utf-8"
            token = self.csrf_token or self._cookie("csrftoken")
            if token:
                headers["X-CSRFToken"] = token

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        status = 200
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", "replace")
        except urllib.error.URLError as exc:
            raise YealinkError(f"transport error: {exc.reason}") from exc
        except OSError as exc:
            raise YealinkError(f"transport error: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            if status >= 400:
                raise YealinkError(f"{method} {path} failed: HTTP {status}") from None
            return {"ret": "ok", "data": raw}

        ret = payload.get("ret")
        if ret in ("ok", "true", True):
            return payload.get("data", payload)
        raise YealinkError(
            f"{method} {path} failed: {payload.get('ret')}",
            error=payload.get("error", payload),
        )

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post(self, path: str, data: Any = None) -> dict:
        """POST a JSON body (what axios does for plain objects)."""
        return self._request("POST", path, data)

    def post_form(self, path: str, data: Any = None) -> dict:
        """POST an application/x-www-form-urlencoded body (used by login)."""
        return self._request("POST", path, data, form=True)

    # ------------------------------------------------------------------- auth

    def rsa_key(self) -> tuple[str, str]:
        """Fetch the per-boot RSA public key (works without login)."""
        try:
            data = self.post(
                "/api/common/info", {"idlist": ["wui.common.rsaN", "wui.common.rsaE"]}
            )
        except YealinkError as exc:
            # The phone returns ret=failed/noauth but still includes the key.
            data = exc.error or {}
        n = data.get("rsaN") or data.get("wui.common.rsaN")
        e = data.get("rsaE") or data.get("wui.common.rsaE")
        if not n or not e:
            raise YealinkError("could not obtain RSA public key", error=data)
        return n, e

    def login(self, username: str | None = None, password: str | None = None) -> dict:
        self.username = username or self.username
        self.password = password or self.password
        if not self.username or self.password is None:
            raise ValueError("username and password are required")

        n, e = self.rsa_key()
        encrypted = "__WUI_ENC__:" + _rsa_encrypt(self.password, n, e)
        result = self.post_form(
            "/api/auth/login", {"username": self.username, "pwd": encrypted}
        )
        self._load_token()
        return result

    def _load_token(self) -> None:
        """Read the CSRF token the web UI sends as ``X-CSRFToken``.

        Request the single key instead of all of ``wui.common``: the full
        group makes the phone log a spurious ``check passwd err``.
        """
        try:
            data = self.post("/api/common/info", {"idlist": ["wui.common.token"]})
        except YealinkError:
            return
        self.csrf_token = data.get("wui.common.token") or None

    def logout(self) -> dict:
        return self.post("/api/auth/logout")

    def user(self) -> dict:
        return self.get("/api/auth/user")

    def is_logged_in(self) -> bool:
        try:
            self.user()
            return True
        except YealinkError:
            return False

    # ------------------------------------------------------------- session cache

    def save_session(self, path: str) -> None:
        """Persist cookies so a restart can reuse the session (chmod 600)."""
        data = {cookie.name: cookie.value for cookie in self._jar}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)

    def load_session(self, path: str) -> bool:
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return False
        for name, value in data.items():
            self._jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=name,
                    value=value,
                    port=None,
                    port_specified=False,
                    domain=self.host,
                    domain_specified=False,
                    domain_initial_dot=False,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                )
            )
        if not self.is_logged_in():
            return False
        self._load_token()
        return True

    # --------------------------------------------------------------- read API

    def info(self, idlist: list[str] | None = None) -> dict:
        """Flat basic-info dict.

        Defaults to ``wui.device.*`` only.  Requesting the whole ``wui`` group
        makes the phone log ``check passwd err`` on every call, because it
        includes the password-related ``wui.common`` fields.
        """
        data = self.post("/api/common/info", {"idlist": idlist or ["wui.device"]})
        if not self.csrf_token:
            self.csrf_token = data.get("wui.common.token") or None
        return data

    def talking(self) -> bool:
        """True while the phone is in a call."""
        return bool(self.get("/api/common/info/status/talking"))

    def accounts(self) -> dict:
        return self.get("/api/account/list")

    def account_status(self) -> dict:
        return self.get("/api/account/status")

    def account_info(self) -> list[dict[str, Any]]:
        return self.get("/api/account/info")

    def calllog(self) -> dict:
        return self.get("/api/contacts/calllog")

    def contacts(self) -> dict:
        return self.get("/api/contacts/localcontacts")

    def wifi(self) -> dict:
        return self.get("/api/network/wifi")

    def wifi_status(self) -> dict:
        return self.get("/api/device/wifiinfo")

    def dsskeys(self) -> dict:
        return self.get("/api/dsskey/info")

    # ------------------------------------------------------------ config (inner)

    def read_config(self, names: list[str], page: str | None = None) -> dict:
        """Read config values.  ``page`` is required by the phone for some keys."""
        path = "/api/inner/readconfig"
        if page:
            path += f"?p={page}"
        data = self.post(path, {"formData": list(names)})
        return (data or {}).get("formData") or {}

    def write_config(self, values: dict, page: str | None = None) -> dict:
        path = "/api/inner/writeconfig"
        if page:
            path += f"?p={page}"
        return self.post(path, {"formData": values})

    def action_uri_allow_list(self) -> list[str]:
        """IPs allowed to trigger Action URIs (Features > Remote Control)."""
        value = self.read_config(["AURILimitIP"], page="FeaturesRemoteControl").get(
            "AURILimitIP"
        )
        if not value:
            return []
        return [part.strip() for part in str(value).split(",") if part.strip()]

    def ensure_action_uri_ip(self, ip: str) -> bool:
        """Add ``ip`` to the Action URI allow list.  Returns True if it was added."""
        allowed = self.action_uri_allow_list()
        if "any" in (entry.lower() for entry in allowed) or ip in allowed:
            return False
        allowed.append(ip)
        self.write_config(
            {"AURILimitIP": ",".join(allowed)}, page="FeaturesRemoteControl"
        )
        return True

    def status(self) -> dict:
        """Unaggregated status blob (works without login)."""
        try:
            return self.get("/api/common/webstatus?noAutoJump=true")
        except YealinkError as exc:
            return exc.error or {}

    # -------------------------------------------------------------- call control

    #: dial type masks used by the web UI
    DIAL_NORMAL = "0"
    DIAL_MANUAL = "1"
    DIAL_DIRECTORY = "3"
    DIAL_HISTORY_DIALED = "16"
    DIAL_HISTORY_MISSED = "17"
    DIAL_HISTORY_RECEIVED = "18"
    DIAL_HISTORY_FORWARDED = "19"

    def dial(
        self,
        number: str,
        account: str = "Auto",
        mask: str = DIAL_MANUAL,
    ) -> dict:
        """Place a call.  ``account`` is an account id ("1") or "Auto"."""
        query = urllib.parse.urlencode({"type": mask, "acc": account, "num": number})
        # the phone rejects body-less POSTs with 403, so send an empty object
        return self.post(f"/api/contacts/dial?{query}", {})

    def hangup(self) -> dict:
        return self.post("/api/contacts/hangup", {})

    # ------------------------------------------------------------------ system

    def reboot(self) -> dict:
        return self.post("/api/system/reboot")

    def restart_web(self) -> dict:
        return self.post("/api/service/restart/web")
