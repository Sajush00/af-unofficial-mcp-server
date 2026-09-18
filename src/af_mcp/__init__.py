"""Unofficial Anytime Fitness client.

Shared core for two adapters: the MCP server (server.py), the primary
interface, and the auth-only CLI (cli.py). Domain code never performs I/O on
import; every network call goes through af_mcp.http.
"""

__version__ = "0.2.0"
