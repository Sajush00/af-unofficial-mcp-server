# af-unofficial-mcp-server

Ask your AI assistant how busy the gym is.

This is a small unofficial tool I built for myself. It lets your AI
assistant answer questions about your Anytime Fitness club: how many people
are in right now (the same live count the official app shows), whether now
is a good time to head over, when it is usually quiet, and how often you
have been going.

Anytime Fitness does not publish an API, so I rebuilt what I needed by
taking the official app apart and asking the same servers it uses. That
also means this can break when they update the app. Unofficial,
unaffiliated, read-only, personal use.

## What you can ask

- "How busy is the gym right now?" You get the live count and how it
  compares to usual, like "6 people in, much quieter than usual."
- "Should I go now?" One of five answers: go now, good time, normal, maybe
  wait, skip it.
- "What is Saturday morning usually like?" The typical pattern for the day,
  hour by hour.
- "Any quieter clubs near me?" Clubs around yours, nearest first, each with
  a live count.
- "How often have I been going?" Your visit history, with your usual day
  and hour.

## Where the numbers come from

- The live count is the club's busy meter, people counted through the door.
  It is the same number the official app shows.
- "Usually" and "typical" mean a 100-day rolling average for that hour, in
  the club's local time. The should-I-go answer compares the live count to
  the usual count for the same hour.
- Visit history is your own check-ins.
- Everything is read-only. It looks, it cannot touch.

## Which gym is "your gym"

Your home club, the one set on your Anytime Fitness account. The server
looks your home club up fresh on every question, so if you change it in the
app, the answers follow.

You can also ask about any other club by its club code, a short identifier
like `AU-0000`. The nearby-clubs answer lists the codes for clubs near you.

## Setting it up

You need [uv](https://docs.astral.sh/uv/) and an assistant that speaks MCP,
the standard way assistants connect to outside tools. Claude Desktop,
Claude Code, and Hermes all work.

**1. Install the code.** Download or clone this project, open a terminal in
its folder, and run:

```bash
uv sync
```

**2. Log in once.** Anytime Fitness texts a code to the number registered
on your account, and the command asks you for it:

```bash
uv run af-gym login --phone +61400000000
```

The login renews itself as long as you use it. It only needs another SMS
after about a month of no use.

**3. Point your assistant at the server.** Pick your client.

Hermes Agent, in `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  af-gym:
    command: uv
    args: ["run", "--directory", "/absolute/path/to/af-unofficial-mcp-server", "af-mcp"]
```

Claude Desktop, in `claude_desktop_config.json`:

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

**4. Ask away.** "Is the gym busy right now?"

## The login and your data

| Command | What it does |
|---|---|
| `uv run af-gym login --phone <number>` | Texts you a login code and saves the session (add `--code` to skip the prompt) |
| `uv run af-gym status` | Shows whether you are logged in and until when |
| `uv run af-gym logout` | Revokes the session and deletes it from your computer |

Logging in needs no password, just the SMS code. The session lives on your
computer at `~/.af_token.json` and goes nowhere except to Anytime Fitness.
No command or tool ever shows the token values.

## For developers

`make check` runs everything: ruff for lint and formatting, mypy for types,
the project's static checks, and the test suite. The tests run offline
against a fake network, so they need no account and no internet.

The MCP server is the product. The CLI does login, status, and logout, and
stays that way on purpose; see [ADR 0004](docs/adr/0004-auth-only-cli.md).
Decisions are recorded in [docs/adr](docs/adr).

| Tool | Answers |
|---|---|
| `occupancy` | Live headcount now, a go-now verdict, and typical counts for the rest of today |
| `forecast` | Typical hourly pattern for a day |
| `nearby_clubs` | Clubs near the home gym, nearest first, each with a live count |
| `visits` | Check-ins in a date range, newest first, with totals and your usual day and hour |
| `auth_status` | Session metadata only, never token values |

### Project layout

```
src/af_mcp/
├── http.py        the only module that touches the network
├── auth.py        SMS login and the token lifecycle
├── transport.py   the API requests the tools need
├── errors.py      typed error classes
├── timeutil.py    club-local time, DST-safe (zoneinfo)
├── clubs.py       home gym, busy meter, nearby search
├── occupancy.py   live occupancy, verdict, forecast
├── visits.py      visit history, bounded windows
├── server.py      where the MCP tools live
└── cli.py         login, status, logout
tools/static_checks.py   project-specific lint rules
tests/                   offline test suite
```

### Why the static checks exist

Each rule in `tools/static_checks.py` names a mistake that already happened.
The rules run inside `make check` and as regular tests, so the suite fails
if the codebase regresses.

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

## Disclaimer

Unofficial and unaffiliated with Anytime Fitness. It uses the app's own
servers with the account owner's credentials, read-only, for personal use.

## License

MIT © 2026 Sajush Arukat. See [LICENSE](LICENSE).
