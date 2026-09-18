# ADR 0003: MCP server plus a small CLI, no REST adapter

## Context

An intermediate version shipped a FastAPI REST adapter next to the MCP
server, with `fastapi` and `uvicorn` as an optional dependency group. The
repository is an MCP server; the REST surface duplicated the same domain
functions behind endpoints nobody called, and it pulled extra dependencies
into the dev environment.

## Decision

The MCP server is the product. A CLI (`af-gym`) stays because the SMS login
flow needs a human at a terminal, and quick shell checks are handy. The
REST adapter and its dependencies are removed.

The rule of thumb going forward: anything that is not required for the
full functioning of the MCP server does not ship.

## Consequences

- Dependencies shrink to `fastmcp` (runtime) plus pytest, ruff, and mypy
  (dev).
- `server.py` and `cli.py` are thin adapters over the same domain modules,
  so the two surfaces cannot drift apart.
- If a REST surface is ever needed, it is a small adapter over the existing
  domain functions; the git history has one to copy from.
