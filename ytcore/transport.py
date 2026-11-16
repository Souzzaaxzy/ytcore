"""HTTP transport for InnerTube.

Defaults to :mod:`urllib` (no dependencies). Tests inject a fake transport so
the parsing and URL logic run for real without touching the network.
"""

from __future__ import annotations

import http.cookiejar
import json as _json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol


@dataclass
class Response:
    status: int
    headers: Dict[str, str]
    body: bytes = b""

    def json(self):
        if not self.body:
            return None
        return _json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Transport(Protocol):
    def post_json(self, url: str, payload: dict, headers: Dict[str, str]) -> Response:
        ...

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Response:
        ...


def read_cookiefile(path: str) -> str:
    """Read a Netscape cookie file into a single ``Cookie:`` header value."""
    pairs = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7 and "youtube" in parts[0]:
                    pairs.append(f"{parts[5]}={parts[6]}")
    except OSError:
        return ""
    return "; ".join(pairs)


class UrllibTransport:
    """Default transport built on :mod:`urllib`.

    A ``cookiefile`` (Netscape format) or a raw ``cookie`` string can be given;
    the cookies are sent on every request and a ``CookieJar`` keeps whatever
    YouTube sets (``VISITOR_INFO1_LIVE``, ``__Secure-*`` ...), which is what
    turns ``LOGIN_REQUIRED`` into a working response for many videos.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        *,
        cookiefile: Optional[str] = None,
        cookie: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.cookiejar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookiejar)
        )
        self.cookie = cookie or (read_cookiefile(cookiefile) if cookiefile else "")
        self.visitor_data: Optional[str] = None

    def _cookie_header(self) -> str:
        if not self.cookie:
            return ""
        return self.cookie

    def post_json(self, url: str, payload: dict, headers: Dict[str, str]) -> Response:
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        for key, value in headers.items():
            req.add_header(key, value)
        if self.cookie:
            req.add_header("Cookie", self._cookie_header())
        return self._send(req)

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Response:
        req = urllib.request.Request(url, method="GET")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        if self.cookie:
            req.add_header("Cookie", self._cookie_header())
        return self._send(req)

    def _send(self, req) -> Response:
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                body = resp.read()
                self._capture_visitor(body)
                return Response(
                    status=resp.status,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=body,
                )
        except urllib.error.HTTPError as exc:
            return Response(
                status=exc.code,
                headers={k.lower(): v for k, v in (exc.headers or {}).items()},
                body=exc.read(),
            )

    def _capture_visitor(self, body: bytes) -> None:
        if self.visitor_data or b"visitorData" not in body[:400000]:
            return
        match = re.search(rb'"visitorData":"(.*?)"', body)
        if match:
            self.visitor_data = match.group(1).decode("utf-8", "replace")


@dataclass
class RecordedCall:
    url: str
    payload: dict
    headers: Dict[str, str] = field(default_factory=dict)


class FakeTransport:
    """In-memory transport for tests.

    ``routes`` maps a substring of the URL (e.g. ``"player"`` or ``"search"``)
    to a payload (returned as JSON) or a callable ``(call) -> dict``.
    """

    def __init__(self, routes: Optional[Dict[str, object]] = None) -> None:
        self.routes = dict(routes or {})
        self.calls: list[RecordedCall] = []
        self.default = {"playabilityStatus": {"status": "OK"}, "streamingData": {}}

    def add(self, needle: str, payload: object) -> "FakeTransport":
        self.routes[needle] = payload
        return self

    def post_json(self, url: str, payload: dict, headers: Dict[str, str]) -> Response:
        call = RecordedCall(url=url, payload=payload, headers=dict(headers))
        self.calls.append(call)
        for needle, handler in self.routes.items():
            if needle in url:
                data = handler(call) if callable(handler) else handler
                return Response(200, {}, _json.dumps(data).encode("utf-8"))
        return Response(200, {}, _json.dumps(self.default).encode("utf-8"))

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Response:
        return Response(200, {}, b"")
