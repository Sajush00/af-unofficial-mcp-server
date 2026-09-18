# af-unofficial-mcp-server

I got tired of opening the AF app before every gym
trip just to check how busy it was, so I built this. Now I just ask my
assistant "how busy is the gym?" and it comes back with the live headcount,
how that compares to normal, and whether now is a good time to go.

It is unofficial. Anytime Fitness does not publish an API, so I took
version 4.5.0 of its app apart, worked out which requests it makes, and made
the same ones. I have used it for a few months without trouble, but changes
to the official app may break it. ## What you can ask

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
for that hour. The server finds the club's timezone from its coordinates so
forecasts and visit dates use local time. If the live count is well below
usual, it says go now. If it is well above usual, it says skip it. In between
you get good time, normal, or maybe wait.

Visit history is just your own check-ins, which is how it figures out when
you usually go.

## Which gym is "my gym"?

Whatever club is set as the home club on your Anytime Fitness account.
The server checks this each time, so it picks up changes made in the app.

You can also ask about a specific club by its code, and if you don't know
other clubs' codes, the nearby command lists them.

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

There is no password, just the SMS code. Tokens are stored in
`~/.af_token.json`. A pending login challenge uses `~/.af_session.json`.
Both files are readable only by your user account, and no command or MCP tool
prints their contents.

The server normally finds the home club's timezone from its coordinates. To
override it, set `AF_CLUB_TZ` to an IANA timezone such as
`Australia/Sydney`, then restart the server.

## For developers

Run every local check with:

```bash
make check
```

That command runs Ruff, mypy, the project-specific static checks, and the
offline test suite. The tests replace the HTTP boundary and never contact
Anytime Fitness.

The MCP server is the main interface. The CLI only handles login, status,
and logout because the SMS step needs direct user input. The reasoning is in
[ADR 0004](docs/adr/0004-auth-only-cli.md), with the other decisions in
[docs/adr](docs/adr).

| Tool | What it returns |
|---|---|
| `occupancy` | Live headcount, a go-now verdict, and typical counts for the rest of the day |
| `forecast` | The typical hourly pattern for a day |
| `nearby_clubs` | Nearby clubs with distance and live headcount |
| `visits` | Check-ins in a date range, totals, and usual visit times |
| `auth_status` | Session metadata without token values |

### Project layout

```text
src/af_mcp/
├── http.py        the only module that opens network connections
├── auth.py        SMS login and token storage
├── transport.py   authenticated Anytime Fitness API requests
├── clubs.py       home club, busy meter, and nearby search
├── occupancy.py   live occupancy, verdicts, and forecasts
├── visits.py      bounded visit history and summaries
├── timeutil.py    club-local time and timezone lookup
├── server.py      MCP tools
└── cli.py         login, status, and logout
tools/static_checks.py   project-specific checks
tests/                   offline test suite
```

## Disclaimer

Unofficial and not affiliated with Anytime Fitness. It uses the app's own
servers with the account owner's credentials, for personal use.

## License

MIT © 2026 Sajush Arukat. See [LICENSE](LICENSE).
