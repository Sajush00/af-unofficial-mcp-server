"""The package's single outbound-HTTP seam.

Only this module talks to the network. Everything else calls request_json,
which keeps the trust boundary small and lets tests replace one function
instead of mocking every call site.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from af_mcp.errors import ApiError, TransportError

TIMEOUT_SECONDS = 30.0


def encode_query(params: dict[str, Any] | list[tuple[str, str]]) -> str:
    """URL-encode query parameters; list values repeat the key (doseq)."""
    return urllib.parse.urlencode(params, doseq=True)


def _open(
    url: str,
    *,
    headers: dict[str, str],
    body: bytes | None,
    method: str,
    timeout: float,
) -> Any:
    """Open one URL as a context manager.

    This function is the only place in the codebase that opens URLs, and its
    callers build URLs from the fixed AF and Cognito hosts only, never from
    user input. The url-open audit (S310) is waived below for that reason.
    """
    request = urllib.request.Request(  # noqa: S310
        url, data=body, headers=headers, method=method
    )
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    method: str = "GET",
    timeout: float = TIMEOUT_SECONDS,
) -> Any:
    """Perform one HTTP request and decode the JSON response.

    Raises ApiError for error statuses and TransportError when no response
    arrives at all. An empty 200 body returns None (some Cognito operations
    reply with no body).
    """
    try:
        with _open(
            url, headers=headers or {}, body=body, method=method, timeout=timeout
        ) as response:
            payload = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise ApiError(exc.code, detail, url.split("?")[0]) from exc
    except urllib.error.URLError as exc:
        raise TransportError(f"Network failure for {url.split('?')[0]}: {exc.reason}") from exc
    if not payload.strip():
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ApiError(status, "response body was not valid JSON", url.split("?")[0]) from exc
