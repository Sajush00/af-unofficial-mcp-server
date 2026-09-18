"""Shared fixtures: fake transport, isolated auth files, offline guard."""

from __future__ import annotations

import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest

from af_mcp import http, timeutil
from factories import write_token

Response = Any | Exception | Callable[[str, dict[str, str], bytes | None], Any]


class FakeAPI:
    """Stands in for af_mcp.http.request_json.

    Routes match by substring against the request URL; the first matching
    route wins. A response is returned as-is, raised when it is an Exception,
    or called with (url, headers, body) when it is a function.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._routes: list[tuple[str, Response]] = []

    def route(self, substring: str, response: Response) -> FakeAPI:
        self._routes.append((substring, response))
        return self

    def __call__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        method: str = "GET",
        timeout: float = 30.0,
    ) -> Any:
        self.calls.append({"url": url, "headers": headers or {}, "body": body, "method": method})
        for substring, response in self._routes:
            if substring in url:
                if isinstance(response, Exception):
                    raise response
                if callable(response):
                    return response(url, headers or {}, body)
                return response
        raise AssertionError(f"no fake route for {url}")


def _refuse(*_args: object, **_kwargs: object) -> NoReturn:
    raise AssertionError("tests must stay offline; use the fake_api fixture")


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No DNS, no TCP connects. asyncio's socketpair self-pipe still works."""
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)


@pytest.fixture(autouse=True)
def _isolated_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test starts logged out, with auth files inside tmp_path."""
    monkeypatch.setenv("AF_TOKEN_FILE", str(tmp_path / "token.json"))
    monkeypatch.setenv("AF_SESSION_FILE", str(tmp_path / "session.json"))
    monkeypatch.setenv("AF_CLUB_TZ", "Australia/Sydney")
    timeutil.club_zone.cache_clear()
    yield tmp_path
    timeutil.club_zone.cache_clear()


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch) -> FakeAPI:
    fake = FakeAPI()
    monkeypatch.setattr(http, "request_json", fake)
    return fake


@pytest.fixture
def auth_env(_isolated_auth: Path) -> Path:
    """A logged-in session: the isolated token file is seeded with a token."""
    write_token(_isolated_auth)
    return _isolated_auth
