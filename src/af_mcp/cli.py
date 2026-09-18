"""Command-line interface: the same data, no agent required."""

from __future__ import annotations

import argparse
import json
import sys

from af_mcp import auth, render, timeutil, transport, visits
from af_mcp.clubs import nearby
from af_mcp.errors import AFError
from af_mcp.occupancy import forecast as build_forecast
from af_mcp.occupancy import go_now_verdict
from af_mcp.occupancy import occupancy as build_occupancy


def cmd_login(args: argparse.Namespace) -> int:
    auth.request_sms_code(args.phone)
    print("Code requested. Cognito will text the phone number registered on the account.")
    print("Next: af-gym verify --code <code>")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    auth.verify_sms_code(args.code)
    print(f"Logged in. Tokens saved (expires in {auth.status().get('accessTokenExpires')}).")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    print(json.dumps(auth.status(), indent=2))
    return 0


def cmd_profile(_args: argparse.Namespace) -> int:
    print(json.dumps(transport.api_get("me/user"), indent=2))
    return 0


def cmd_gym(_args: argparse.Namespace) -> int:
    from af_mcp.clubs import home_gym

    print(json.dumps(home_gym(), indent=2))
    return 0


def cmd_occupancy(args: argparse.Namespace) -> int:
    result = build_occupancy(args.club)
    print(f"{result['name']} ({result['afNumber']})")
    if result["currentMemberCount"] is not None:
        print(
            f"Now: {result['currentMemberCount']} people "
            f"({result['busyPercent']}% of typical peak {result['maxAverageUsage']})"
        )
    else:
        print("No live occupancy for this club. Try `forecast` for typical values.")
    print(render.bar_chart(result["restOfDay"], "Rest of today (typical):"))
    return 0


def cmd_forecast(args: argparse.Namespace) -> int:
    result = build_forecast(args.day, args.club)
    title = (
        f"{result['weekday']} {result['date']} at {result['name']} ({result['afNumber']}), typical:"
    )
    print(render.bar_chart(result["hours"], title))
    return 0


def cmd_nearby(args: argparse.Namespace) -> int:
    gym, clubs = nearby(args.radius, args.limit)
    print(f"Clubs within {args.radius} km of {gym['name']} ({gym['afNumber']}):")
    print()
    for club in clubs:
        live = (
            f"{club['currentMemberCount']} in now"
            if club["currentMemberCount"] is not None
            else "no live data"
        )
        star = " <- home" if club["isHomeGym"] else ""
        print(
            f"  {club['afNumber']:<8} {club['name']:<28} {club['distanceKm']:>5} km  "
            f"{club['status'] or '':<9} {live}{star}"
        )
        print(f"           {club['address']}")
    return 0


def cmd_visits(args: argparse.Namespace) -> int:
    stats = visits.visit_stats(args.months)
    if not stats.get("visits"):
        print("No visits found.")
        return 0
    print(f"{stats['visits']} visits since {stats['since']}")
    print()
    print(render.heatmap(stats))
    print()
    print("Legend: . none   lower blocks light, higher blocks busy")
    print(f"Most common day: {stats['mostCommonDay'][0]} ({stats['mostCommonDay'][1]} visits)")
    print(f"Most common hour: {stats['mostCommonHour']}")
    print(f"Last visit: {stats['lastVisit']}")
    return 0


def cmd_when(_args: argparse.Namespace) -> int:
    result = go_now_verdict()
    print(f"{result['name']} ({result['afNumber']}), {timeutil.moment_string(timeutil.now())}")
    if result.get("verdict") in ("no-live-data", "no-baseline"):
        print(result["message"])
        return 0
    percent = round((result["ratio"] - 1) * 100)
    if percent == 0:
        difference = "exactly typical"
    else:
        direction = "busier" if percent > 0 else "quieter"
        difference = f"{abs(percent)}% {direction} than usual"
    print(
        f"Now: {result['currentMemberCount']} people "
        f"(typical: {result['typicalCount']}) - {difference}."
    )
    print(render.VERDICT_TEXT[result["verdict"]])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="af-gym",
        description="Anytime Fitness client (unofficial).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="request an SMS login code")
    p.add_argument("--phone", required=True, help="phone in E.164 format, e.g. +61400000000")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("verify", help="verify the SMS code and save tokens")
    p.add_argument("--code", required=True)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("status", help="show session metadata (never token values)")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("profile", help="show account details")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("gym", help="show home gym details")
    p.set_defaults(func=cmd_gym)

    p = sub.add_parser("occupancy", help="live headcount + rest-of-day typical")
    p.add_argument("club", nargs="?", help="club af-number (default: home gym)")
    p.set_defaults(func=cmd_occupancy)

    p = sub.add_parser("forecast", help="typical hourly pattern for a day")
    p.add_argument("club", nargs="?", help="club af-number (default: home gym)")
    p.add_argument(
        "--day",
        default="tomorrow",
        help="'today', 'tomorrow', or a weekday name (default: tomorrow)",
    )
    p.set_defaults(func=cmd_forecast)

    p = sub.add_parser("nearby", help="clubs around your home gym with live counts")
    p.add_argument("--radius", type=int, default=25, help="search radius in km (default 25)")
    p.add_argument("--limit", type=int, default=5, help="max clubs (default 5)")
    p.set_defaults(func=cmd_nearby)

    p = sub.add_parser("visits", help="visit history with heatmap")
    p.add_argument("--months", type=int, default=12, help="lookback months (default 12)")
    p.set_defaults(func=cmd_visits)

    p = sub.add_parser("when", help="go-now verdict: live count vs typical for this hour")
    p.set_defaults(func=cmd_when)

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
