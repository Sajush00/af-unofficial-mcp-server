# af-unofficial-mcp-server

I go to Anytime Fitness and I got tired of opening the app before every gym
trip just to check how busy it was, so I built this. Now I just ask my
assistant "how busy is the gym?" and it comes back with the live headcount,
how that compares to normal, and whether now is a good time to go.

It is unofficial. Anytime Fitness does not publish an API, so I took
version 4.5.0 of their app apart, worked out which requests it makes, and
made the same ones. It will break when they change something on their side,
and hopefully I fix it when it does. ## What you can ask

- "How busy is it right now?" The live count, plus how it compares to the
  usual crowd for this hour.
- "Should I go now?" One of five answers: go now, good time, normal, maybe
  wait, skip it.
- "When is it quiet on a Saturday?" The typical pattern hour by hour, so
  you can find a quiet window.
- "Any quieter clubs nearby?" Clubs around yours, nearest first, with live
  counts.
- "How often have I been going?" Your check-in history, plus the day and
  hour you usually go.

## How it works

The whole thing comes down to two numbers: how many people are in right
now, and how many are usually there around this time.

The first one comes straight from the club's door counters, the same busy
meter the official app shows you. The second is a 100-day rolling average
for that hour, in the club's local time. If the live count is way below
usual, it says go now, and if it is way above, it says skip it. In between
you get good time, normal, or maybe wait.

Visit history is just your own check-ins, which is how it figures out when
you usually go.

## Which gym is "my gym"?

Whatever club is set as the home club on your Anytime Fitness account.
Mine is AU-0000, the Example Club club in Sydney. The server checks this every
time, so if you switch your home club in the app, it picks that up.

You can also ask about a specific club by its code, and if you don't know
other clubs' codes, the nearby answer lists them.

## Setting it up

You need [uv](https://docs.astral.sh/uv/) and an assistant that can use
MCP servers, which covers Claude Desktop, Claude Code, and Hermes.

**1. Get the code.** Download or clone the repo, open a terminal in its
folder, and run:

```bash
uv sync
```

**2. Log in once.** Anytime Fitness texts a code to the phone number on
your account, and this asks you for it:

```bash
uv run af-gym login --phone +61400000000
```

The session renews itself after that, so you only need another text if it
goes unused for about a month.

**3. Point your assistant at it.** Add the server to your client:

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

**4. Ask it something.** "Is the gym busy right now?"

## The login and your data

| Command | What it does |
|---|---|
| `uv run af-gym login --phone <number>` | Logs in by SMS; pass `--code` to skip the prompt |
| `uv run af-gym status` | Says whether you are logged in, and until when |
| `uv run af-gym logout` | Revokes the session and deletes it from your computer |

There is no password, just the SMS code. The session file sits at
`~/.af_token.json` on your machine and goes nowhere except Anytime Fitness.
No command or tool ever prints the token values.

## For developers

`make check` runs everything: ruff for lint and formatting, mypy for types,
a bunch of custom lint rules for this project, and the test suite. The tests
never touch the network, so they need no account and no internet.

The MCP server is the product. The CLI does login, status, and logout, and
stays that way on purpose, with the reasoning in
[ADR 0004](docs/adr/0004-auth-only-cli.md). The other decisions are in
[docs/adr](docs/adr).

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
├── timeutil.py    club-local time, DST-safe via zoneinfo
├── clubs.py       home gym, busy meter, nearby search
├── occupancy.py   live occupancy, verdict, forecast
├── visits.py      visit history, bounded windows
├── server.py      where the MCP tools live
└── cli.py         login, status, logout
tools/static_checks.py   project-specific lint rules
tests/                   offline test suite
```

## Disclaimer

Unofficial and not affiliated with Anytime Fitness. It uses the app's own
servers with the account owner's credentials, for personal use.

## License

MIT © 2026 Sajush Arukat. See [LICENSE](LICENSE).
