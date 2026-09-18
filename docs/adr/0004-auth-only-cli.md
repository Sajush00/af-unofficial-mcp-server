# ADR 0004: The MCP server is the primary interface; the CLI is auth-only

## Context

The first version mirrored the MCP tools on the CLI: `occupancy`, `forecast`,
`nearby`, `visits`, `when`, plus raw-JSON `profile` and `gym`. Every query
existed twice, and keeping the two in step forced a third module (`render.py`)
that only the CLI used. Meanwhile the MCP tools returned bare numbers where
the CLI had already reasoned about them (the go-now verdict, the visit
habits), so the agent got the weaker half.

The one thing an agent cannot do by itself is the SMS login: the code arrives
on a phone and a human reads it out.

## Decision

The MCP server is the primary interface and the only query surface. The CLI
exposes exactly three commands, all auth:

- `af-gym login --phone <n> [--code <c>]` — request the SMS code and verify
  it in one step; the code is prompted for unless `--code` is given.
- `af-gym status` — saved-session state, never token values.
- `af-gym logout` — revoke the refresh token (best effort) and delete local
  state.

Every query command is removed, and with them `render.py`. Where the CLI had
a richer answer than the tool, the tool gained the field instead: `occupancy`
now returns `verdict`/`verdictMessage`/`ratio`/`typicalCount`, and `visits`
returns `mostCommonDay`/`mostCommonHour` (the heatmap grid existed only for
the CLI and goes away with it).

Static check AF010 enforces the split: `cli.py` may not import `clubs`,
`occupancy`, `visits`, or `transport`.

This supersedes the "quick shell checks are handy" clause of ADR 0003.

## Consequences

- One place to add or change a query: the MCP tool list (five tools, down
  from seven; `go_now_verdict` folded into `occupancy`, `visit_stats` into
  `visits`).
- `af-gym logout` closes the auth loop; before this, clearing the session
  meant deleting `~/.af_token.json` by hand.
- The two surfaces cannot drift, because there is only one query surface.
- If a shell query is ever missed, the fix is to call the MCP tool, not to
  grow the CLI back; AF010 fails the build if the query modules reappear in
  `cli.py`.
