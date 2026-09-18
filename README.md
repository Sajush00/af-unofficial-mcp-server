# AF Unofficial MCP Server

Unofficial [MCP](https://modelcontextprotocol.io) server that gives any AI agent
read-only access to your Anytime Fitness data: live gym occupancy, typical busy
patterns, nearby clubs with live counts, and visit history.

Built against the *AF App 4.5.0* (Android) API.

## Tools

| Tool | Returns |
|---|---|
| `occupancy` | Live member count now + typical counts for the rest of today |
| `forecast` | Typical hourly pattern for any day (100-day rolling averages) |
| `go_now_verdict` | Go / wait / skip verdict: live count vs typical for this hour |
| `nearby_clubs` | Clubs near the home gym, nearest first, each with a live count |
| `visit_stats` | Visit totals, most common day/hour, last visit, weekday x hour heatmap |
| `visit_history` | Check-ins in a date range (default: last 90 days), newest first, with range totals and consistency counters |
| `auth_status` | Whether the saved session exists and refreshes (no token values) |

## Quick start

```bash
# 1. One-time login (SMS code to your phone)
uv run af_api.py login --phone +61400000000
uv run af_api.py verify --code 123456

# 2. Run the MCP server (stdio; an MCP client normally launches this for you)
uv run server.py
```

## Connect an agent

**Hermes Agent** (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  af-gym:
    command: uv
    args: ["run", "/absolute/path/to/server.py"]
```

or: `hermes mcp add af-gym --command uv --args run /absolute/path/to/server.py`

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "af-gym": { "command": "uv", "args": ["run", "/absolute/path/to/server.py"] }
  }
}
```

**Claude Code**: `claude mcp add af-gym -- uv run /absolute/path/to/server.py`

Any MCP client that can spawn a stdio server works the same way. The server is
written against the standalone [FastMCP](https://gofastmcp.com) package, so its
environment is fully managed by uv (per-script dependencies).

## Auth model

- Tokens live at `~/.af_token.json`, on this machine only. Token values are never
  returned by any tool.
- Access token lasts 24 h and the server refreshes it silently.
- Refresh token lasts ~30 days and is not rotated, so one SMS login sustains
  around a month of use and keeps renewing while used.
- After ~30 idle days, `auth_status` reports the session is gone and a fresh
  SMS login is due.

## Why

Personal utility: "is the gym worth going to right now?" deserves a one-line
answer, and the agent that already knows my schedule is the right place to ask.
It is also a neat sandbox for agent tool-use: seven read-only tools over live
structured data with a real auth flow.

## Disclaimer

Unofficial and unaffiliated with Anytime Fitness. Uses the app's own endpoints
with your own account, read-only, for personal use.

## Files

| File | What it is |
|---|---|
| `server.py` | The FastMCP server (this project) |
| `af_api.py` | The client + CLI (also serves a REST API: `uv run af_api.py serve`) |
