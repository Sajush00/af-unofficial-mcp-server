"""Authenticated calls against the AF mobile API."""

from __future__ import annotations

from typing import Any

from af_mcp import auth, http

API_BASE = "https://api.sebrands.com/mobile/api"
API_HEADERS = {"Api-Version": "5.0", "Accept": "application/json"}


def api_get(path: str, params: dict[str, Any] | list[tuple[str, str]] | None = None) -> Any:
    """GET one API path with the stored session attached.

    params may be a mapping, or a list of pairs when a key repeats (the
    busy-meter batch endpoint needs repeated afNumbers parameters).
    """
    url = f"{API_BASE}/{path}"
    if params:
        url = f"{url}?{http.encode_query(params)}"
    headers = {**API_HEADERS, "Authorization": f"Bearer {auth.access_token()}"}
    return http.request_json(url, headers=headers)
