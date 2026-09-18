"""Tests for the MCP tool surface: names, results, and error translation."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from af_mcp import server
from factories import busy_meter
from factories import home_gym as home_gym_payload
from factories import visits as visits_payload

EXPECTED_TOOLS = {
    "occupancy",
    "forecast",
    "nearby_clubs",
    "visits",
    "auth_status",
}


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    async def run() -> Any:
        async with Client(server.mcp) as client:
            return await client.call_tool(name, arguments or {})

    return asyncio.run(run())


def test_tool_surface_is_exactly_the_documented_set(fake_api, auth_env):
    async def names() -> set[str]:
        async with Client(server.mcp) as client:
            return {tool.name for tool in await client.list_tools()}

    assert asyncio.run(names()) == EXPECTED_TOOLS


def test_visits_tool_returns_the_windowed_summary(fake_api, auth_env):
    fake_api.route("gym-visit", visits_payload([("2026-09-10T02:16:19Z", "Example Club")]))
    result = call_tool("visits", {"start": "2026-09-01", "end": "2026-09-18"})
    data = result.data
    assert data["totalInRange"] == 1
    assert data["visits"][0]["club"] == "Example Club"
    assert data["range"] == {"start": "2026-09-01", "end": "2026-09-18"}


def test_occupancy_tool_carries_the_verdict_fields(fake_api, auth_env):
    fake_api.route("my-gym", home_gym_payload())
    fake_api.route("busy-meter", busy_meter(current=7, peak=50))
    data = call_tool("occupancy").data
    assert data["currentMemberCount"] == 7
    assert data["afNumber"] == "AU-0000"
    # The fixture has no weekDays, so there is no baseline for this hour.
    assert data["verdict"] == "no-baseline"
    assert data["verdictMessage"]


def test_auth_errors_become_tool_errors_with_a_login_hint(fake_api):
    with pytest.raises(ToolError, match="login"):
        call_tool("occupancy")


def test_bad_input_becomes_a_tool_error(fake_api, auth_env):
    with pytest.raises(ToolError, match="after"):
        call_tool("visits", {"start": "2026-09-10", "end": "2026-09-01"})


def test_transport_errors_become_tool_errors(fake_api, auth_env):
    from af_mcp.errors import TransportError

    fake_api.route("my-gym", home_gym_payload())
    fake_api.route("busy-meter", TransportError("network down"))
    with pytest.raises(ToolError, match="network down"):
        call_tool("occupancy")


def test_auth_status_never_leaks_token_values(fake_api, auth_env):
    data = call_tool("auth_status").data
    assert data["loggedIn"] is True
    assert "test-access" not in str(data)


def test_every_tool_is_documented():
    async def descriptions() -> dict[str, str | None]:
        async with Client(server.mcp) as client:
            return {tool.name: tool.description for tool in await client.list_tools()}

    tools = asyncio.run(descriptions())
    assert set(tools) == EXPECTED_TOOLS
    for name, description in tools.items():
        assert description and description.strip() != "None", f"{name} has no description"
