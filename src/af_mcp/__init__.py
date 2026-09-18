"""Unofficial Anytime Fitness client.

Shared core for two adapters: the MCP server (server.py) and the CLI
(cli.py). Domain code never performs I/O on import; every network call goes
through af_mcp.http.
"""

__version__ = "0.2.0"
