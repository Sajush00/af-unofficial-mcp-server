"""Command-line auth for the AF MCP server.

The MCP server is the primary interface for queries; this CLI exists only for
the parts an agent cannot do itself: reading the SMS code off the phone and
keeping the saved session in order.
"""

from __future__ import annotations

import argparse
import sys

from af_mcp import auth
from af_mcp.errors import AFError


def cmd_login(args: argparse.Namespace) -> int:
    """Request an SMS code and verify it, saving the session."""
    auth.request_sms_code(args.phone)
    print("Code requested. Cognito texts the number registered on the account.")
    code = args.code
    if not code:
        try:
            code = input("SMS code: ").strip()
        except EOFError:
            print(
                "No code entered. Re-run: af-gym login --phone <number> --code <code>.",
                file=sys.stderr,
            )
            return 1
        except KeyboardInterrupt:
            print("\nCancelled.", file=sys.stderr)
            return 1
    auth.verify_sms_code(code)
    expires = auth.status().get("accessTokenExpires")
    print(f"Logged in. Access token expires {expires}.")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    """Print one line of session state (never token values)."""
    state = auth.status()
    if state.get("loggedIn"):
        auto = "auto-refresh on" if state.get("autoRefresh") else "no auto-refresh"
        print(f"Logged in ({auto}). Access token expires {state['accessTokenExpires']}.")
    else:
        print(state.get("detail", "Not logged in."))
    return 0


def cmd_logout(_args: argparse.Namespace) -> int:
    """Revoke the refresh token (best effort) and delete local tokens."""
    result = auth.logout()
    if not result["hadSession"]:
        print("No saved session.")
    elif result["revoked"]:
        print("Logged out. Refresh token revoked and local state deleted.")
    else:
        print("Logged out locally. The refresh token expires on its own.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="af-gym",
        description="Auth for the AF MCP server (login, status, logout).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="log in with an SMS code")
    p.add_argument("--phone", required=True, help="phone in E.164 format, e.g. +61400000000")
    p.add_argument("--code", help="SMS code; skips the prompt (useful in scripts)")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("status", help="show the saved session state")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("logout", help="revoke the session and delete local tokens")
    p.set_defaults(func=cmd_logout)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one CLI command; returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except AFError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
