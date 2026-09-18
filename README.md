# af-unofficial-mcp-server

Unofficial MCP server for Anytime Fitness data: live gym occupancy, busy
forecasts, nearby clubs, and personal visit history. It talks to the AF App
4.5.0 mobile API. Read-only, single
account, personal use.

The MCP server is the primary interface. The `af-gym` CLI exists only for
the SMS login flow — the one thing an agent cannot do by itself.

## Tools

| Tool | Returns |
|---|---|
| `occupancy` | Live headcount now, a go-now verdict, and typical counts for the rest of today |
| `forecast` | Typical hourly pattern for a day (100-day rolling averages) |
| `nearby_clubs` | Clubs near the home gym, nearest first, each with a live count |
| `visits` | Check-ins in a date range, newest first, with totals and your usual day and hour |
| `auth_status` | Session metadata only, never token values |

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync

# One-time login. Cognito texts a code to the number registered with the club;
# the command prompts for it. Add --code to run it non-interactively.
uv run af-gym login --phone +61400000000

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

Authentication only. Queries live on the MCP server (see
[ADR 0004](docs/adr/0004-auth-only-cli.md)); the CLI cannot grow query
commands back.

| Command | Does |
|---|---|
| `af-gym login --phone <n> [--code <c>]` | SMS login in one step; prompts for the code, `--code` for scripts |
| `af-gym status` | Session metadata, never token values |
| `af-gym logout` | Revoke the refresh token and delete local tokens |

## How it is built

```
src/af_mcp/
├── http.py        the only module that touches the network
├── auth.py        Cognito SMS login, token lifecycle
├── transport.py   authenticated GETs against the mobile API
├── errors.py      typed error hierarchy
├── timeutil.py    club-local time (zoneinfo, DST-correct)
├── clubs.py       home gym, busy meter, nearby search
├── occupancy.py   live occupancy + go-now verdict, forecast
├── visits.py      windowed visit history
├── server.py      the MCP tool surface
└── cli.py         auth commands only (login, status, logout)
tools/static_checks.py   project-specific lint rules (see below)
tests/                   offline test suite (fake transport, no sockets)
```

`server.py` is the product; `cli.py` stays small because reading an SMS code
off a phone is the one step no agent can take for you.

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
| AF010 | `cli.py` imports `clubs`, `occupancy`, `visits`, or `transport` | The CLI is auth-only (ADR 0004); querying lives on the MCP side so the two surfaces cannot drift |

## Auth model

- Tokens live at `~/.af_token.json` (override: `AF_TOKEN_FILE`). The file is
  outside the repository and never committed.
- Access tokens last 24 hours and refresh silently.
- Refresh tokens last about 30 days and are not rotated, so one SMS login
  covers roughly a month of use. After ~30 idle days, `auth_status` reports
  the session is gone and a fresh login is due.
- `af-gym logout` revokes the refresh token (best effort) and deletes the
  local state.
- No tool ever returns token values.

## Disclaimer

Unofficial and unaffiliated with Anytime Fitness. Uses the app's own
endpoints with the account owner's credentials, read-only, for personal use.

## License

MIT © 2026 Sajush Arukat. See [LICENSE](LICENSE).
