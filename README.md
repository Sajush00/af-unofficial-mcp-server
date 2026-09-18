# af-unofficial-mcp-server

Unofficial MCP server for Anytime Fitness data: live gym occupancy, busy
forecasts, nearby clubs, and personal visit history. It talks to the AF App
4.5.0 mobile API. Read-only, single
account, personal use.

## Tools

| Tool | Returns |
|---|---|
| `occupancy` | Live headcount now, plus typical counts for the rest of today |
| `forecast` | Typical hourly pattern for a day (100-day rolling averages) |
| `go_now_verdict` | Go, wait, or skip, comparing the live count to this hour's typical |
| `nearby_clubs` | Clubs near the home gym, nearest first, each with a live count |
| `visit_stats` | Visit totals, most common day and hour, weekday x hour heatmap |
| `visit_history` | Check-ins in a date range, newest first, with range totals |
| `auth_status` | Session metadata only, never token values |

## Quick start

```bash
uv sync

# One-time login. Cognito texts the code to the number registered with the club.
uv run af-gym login --phone +61400000000
uv run af-gym verify --code 123456

# Run the MCP server (stdio; MCP clients usually launch it for you)
uv run af-mcp
```

## Connect an agent

Hermes Agent (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  af-gym:
    command: uv
    args: ["run", "--directory", "/absolute/path/to/af-unofficial-mcp-server", "af-mcp"]
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "af-gym": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/af-unofficial-mcp-server", "af-mcp"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add af-gym -- uv run --directory /absolute/path/to/af-unofficial-mcp-server af-mcp
```

## CLI

The same data from a shell. Useful for the login flow and quick checks.

| Command | Does |
|---|---|
| `af-gym login --phone <n>` / `verify --code <c>` | SMS login, saves the session |
| `af-gym status` | Session metadata, never token values |
| `af-gym occupancy [club]` | Live headcount and rest-of-day typical |
| `af-gym forecast [club] --day saturday` | Typical hourly pattern |
| `af-gym nearby --radius 15` | Clubs around home with live counts |
| `af-gym visits --months 12` | Visit heatmap and totals |
| `af-gym when` | Go-now verdict for this hour |
| `af-gym profile` / `gym` | Raw account and home-club JSON |

## How it is built

```
src/af_mcp/
├── http.py        the only module that touches the network
├── auth.py        Cognito SMS login, token lifecycle
├── transport.py   authenticated GETs against the mobile API
├── errors.py      typed error hierarchy
├── timeutil.py    club-local time (zoneinfo, DST-correct)
├── clubs.py       home gym, busy meter, nearby search
├── occupancy.py   occupancy, forecast, verdict
├── visits.py      windowed visit history and stats
├── render.py      text rendering for the CLI
├── server.py      the MCP tool surface
└── cli.py         the CLI surface
tools/static_checks.py   project-specific lint rules (see below)
tests/                   offline test suite (fake transport, no sockets)
```

`server.py` and `cli.py` are thin adapters over the same domain modules, so
both surfaces return identical numbers for identical questions.

## Checks

`make check` runs, in order:

1. `ruff check` with a broad rule set (see `pyproject.toml`)
2. `mypy` (typed defs required across the package)
3. `tools/static_checks.py`, project-specific rules
4. `pytest`, the offline test suite

Rules in `tools/static_checks.py` exist because each one names a mistake
that already happened. They run in CI-of-one (`make check`) and as regular
tests, so the suite fails when the codebase regresses:

| Rule | Fails when | Because |
|---|---|---|
| AF001 | `raise SystemExit` or `sys.exit` outside a `__main__` guard | The first version killed the MCP server process on a missing token instead of returning an error |
| AF002 | `timezone(timedelta(...))` appears anywhere | A hardcoded +10 offset was an hour wrong for half the year (Sydney uses +11 in summer) |
| AF003 | `datetime.now()`/`today()` appears outside `timeutil.py` | Ad-hoc clock reads made tests time-dependent and hid the DST bug |
| AF004 | `urllib` is imported outside `http.py` | One network seam means one place to fake, time out, and audit |
| AF005 | a `gym-visit` fetch misses `startDate` or `endDate` | Unbounded pulls dump whole history into agent context for no benefit |
| AF006 | an `@mcp.tool` has no docstring | The docstring is the description the agent sees; an undocumented tool gets misused |
| AF007 | a test imports `urllib.request`, `socket`, `requests`, or `httpx` | Tests replay recorded shapes; the suite must never depend on the network (conftest imports `socket` exactly once, to block it) |
| AF008 | `src` raises a builtin exception (`ValueError`, `RuntimeError`, ...) | The first version raised `RuntimeError` from deep code; callers could not tell "log in" from "API is down" |
| AF009 | a network call runs at import time | Importing a module must never touch the network; tools fetch, imports do not |

## Auth model

- Tokens live at `~/.af_token.json` (override: `AF_TOKEN_FILE`). The file is
  outside the repository and never committed.
- Access tokens last 24 hours and refresh silently.
- Refresh tokens last about 30 days and are not rotated, so one SMS login
  covers roughly a month of use. After ~30 idle days, `auth_status` reports
  the session is gone and a fresh login is due.
- No tool ever returns token values.

## Disclaimer

Unofficial and unaffiliated with Anytime Fitness. Uses the app's own
endpoints with the account owner's credentials, read-only, for personal use.
