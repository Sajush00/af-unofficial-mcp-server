# af-unofficial-mcp-server

An unofficial MCP server for Anytime Fitness. Ask your assistant how busy the
gym is, when it will be quieter, which nearby clubs are less crowded, or how
often you have visited.

It uses the same private API as version 4.5.0 of the Anytime Fitness app. The
API may change without warning. This project is not affiliated with Anytime
Fitness.

## Tools

| Tool | What it returns |
|---|---|
| `occupancy` | Live headcount, how it compares with the usual crowd, and a go-now verdict |
| `forecast` | Typical hourly attendance for a chosen day |
| `nearby_clubs` | Nearby clubs, distance, opening status, and live headcount |
| `visits` | Visit history and common visit times |
| `auth_status` | Login status without exposing tokens |

Attendance comparisons use the club's 100-day hourly averages. The server
finds the home club and its timezone from your account.

## Setup

You need Python 3.11 or later, [uv](https://docs.astral.sh/uv/), and an
MCP-compatible client.

```bash
git clone https://github.com/Sajush00/af-unofficial-mcp-server.git
cd af-unofficial-mcp-server
uv sync
uv run af-gym login --phone +61400000000
```

The login command sends an SMS code to the phone number registered with your
Anytime Fitness account and prompts you to enter it.

### Claude Desktop

Add this to `claude_desktop_config.json`:

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

### Claude Code

```bash
claude mcp add af-gym -- uv run --directory /absolute/path/to/af-unofficial-mcp-server af-mcp
```

### Hermes Agent

Add this to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  af-gym:
    command: uv
    args: ["run", "--directory", "/absolute/path/to/af-unofficial-mcp-server", "af-mcp"]
```

Then ask your assistant: "How busy is the gym right now?"

## Authentication and privacy

```bash
uv run af-gym status
uv run af-gym logout
```

Tokens are stored in `~/.af_token.json`. Pending login details use
`~/.af_session.json`. Both files are private to your user account, and the CLI
and MCP tools never print their contents.

Set `AF_CLUB_TZ` to an IANA timezone such as `Australia/Sydney` if you need to
override automatic timezone detection.

## Development

```bash
make check
```

This runs Ruff, mypy, project-specific static checks, and the offline test
suite. Implementation notes are in [docs/adr](docs/adr).

## License

[MIT](LICENSE) © 2026 Sajush Arukat
