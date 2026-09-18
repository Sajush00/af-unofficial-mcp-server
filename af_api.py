#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["fastapi>=0.110", "uvicorn>=0.29"]
# ///
"""
Anytime Fitness gym occupancy client.

Unofficial client for the AF App 4.5.0 (Android) API.

CLI usage:
  af_api.py login --phone +61400000000        # request SMS login code
  af_api.py verify --code 123456              # complete login, saves token
  af_api.py profile                           # account details
  af_api.py gym                               # home gym details
  af_api.py occupancy [CLUB]                  # live headcount + rest of day
  af_api.py forecast [CLUB] --day tomorrow    # typical hourly pattern (day name or tomorrow/today)
  af_api.py nearby --radius 15 --limit 6      # clubs around home gym + live counts
  af_api.py visits --months 12                # visit history heatmap
  af_api.py when                              # go-now verdict (live vs typical)
  af_api.py serve --port 8000                 # expose as REST API (Swagger at /docs)
"""
# ------------------------------------------------------------------ stdlib
import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime as dt, timezone, timedelta
from pathlib import Path

COGNITO_URL = "https://cognito-idp.us-east-1.amazonaws.com/"
COGNITO_CLIENT_ID = "r56fk5c6c5gfaegh5j673hdeq"
API_BASE = "https://api.sebrands.com/mobile/api"
API_HEADERS_BASE = {"Api-Version": "5.0", "Accept": "application/json"}
TOKEN_FILE = Path.home() / ".af_token.json"
SESSION_FILE = Path(__file__).parent / ".af_session.json"
SYDNEY = timezone(timedelta(hours=10))


# ------------------------------------------------------------------ auth
def cognito(op: str, body: dict) -> dict:
    req = urllib.request.Request(
        COGNITO_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": f"AWSCognitoIdentityProviderService.{op}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def request_sms_code(phone: str) -> None:
    """Request an SMS login code for the account."""
    resp = cognito("InitiateAuth", {
        "AuthFlow": "USER_AUTH",
        "AuthParameters": {
            "USERNAME": phone,
            "PREFERRED_CHALLENGE": "SMS_OTP",
        },
        "ClientId": COGNITO_CLIENT_ID,
        "ClientMetadata": {"deliveryChannel": "sms"},
    })
    session = resp.get("Session")
    if not session:
        raise SystemExit(f"Failed to send SMS: {json.dumps(resp, indent=2)}")
    SESSION_FILE.write_text(json.dumps({
        "phone": phone,
        "session": session,
        "challenge": resp.get("ChallengeName", "SMS_OTP"),
    }))
    print("Code requested. Cognito will text the phone number registered on the account.")
    print("Next: af_api.py verify --code <code>")


def verify_sms_code(code: str) -> None:
    if not SESSION_FILE.exists():
        raise SystemExit("No active login session. Run: af_api.py login --phone <number>")
    state = json.loads(SESSION_FILE.read_text())
    resp = cognito("RespondToAuthChallenge", {
        "ChallengeName": state.get("challenge", "SMS_OTP"),
        "ClientId": COGNITO_CLIENT_ID,
        "Session": state["session"],
        "ChallengeResponses": {
            "USERNAME": state["phone"],
            "SMS_OTP_CODE": code,
        },
    })
    auth = resp.get("AuthenticationResult")
    if not auth:
        raise SystemExit(f"Verification failed: {json.dumps(resp, indent=2)}")
    _save_tokens(auth)
    SESSION_FILE.unlink(missing_ok=True)
    print(f"Logged in. Token saved to {TOKEN_FILE} (expires in {auth.get('ExpiresIn')}s)")


def _save_tokens(auth: dict) -> None:
    auth["expires_at"] = time.time() + auth.get("ExpiresIn", 3600)
    TOKEN_FILE.write_text(json.dumps(auth))


def refresh_tokens() -> dict:
    tok = json.loads(TOKEN_FILE.read_text())
    resp = cognito("GetTokensFromRefreshToken", {
        "RefreshToken": tok["RefreshToken"],
        "ClientId": COGNITO_CLIENT_ID,
    })
    auth = resp.get("AuthenticationResult")
    if not auth:
        raise SystemExit(
            "Refresh token expired — re-login with: af_api.py login --phone <number>\n"
            + json.dumps(resp, indent=2)
        )
    if "RefreshToken" not in auth:
        auth["RefreshToken"] = tok["RefreshToken"]
    _save_tokens(auth)
    return auth


def get_access_token() -> str:
    if not TOKEN_FILE.exists():
        raise SystemExit("Not logged in. Run: af_api.py login --phone <number>")
    tok = json.loads(TOKEN_FILE.read_text())
    if time.time() > tok.get("expires_at", 0) - 60:
        tok = refresh_tokens()
    return tok["AccessToken"]


# ------------------------------------------------------------------ api
def api_get(path: str, params: dict | list | None = None) -> object:
    url = f"{API_BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {get_access_token()}",
        **API_HEADERS_BASE,
    })
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} for {path}: {e.read().decode()[:300]}") from e


def home_gym() -> dict:
    return api_get("me/user/my-gym")["clubProfile"]


def busy_meter(af_number: str) -> dict:
    return api_get(f"clubs/{af_number}/busy-meter")


def resolve_club(af_number: str | None) -> tuple[str, str]:
    """Return (af_number, name), defaulting to home gym."""
    if af_number:
        return af_number, af_number
    gym = home_gym()
    return gym["afNumber"], gym["name"]


def parse_utc(ts: str) -> dt:
    return dt.fromisoformat(ts.replace("Z", "+00:00"))


def find_day_usages(data: dict, weekday: str) -> list[dict] | None:
    for day in data.get("weekDays") or []:
        if day["weekDay"] == weekday:
            return sorted(day["averageUsages"], key=lambda u: u["startTime"])
    return None


def fetch_visits(months: int = 12) -> list[dt]:
    end = dt.now(timezone.utc)
    start = end - timedelta(days=30 * months)
    data = api_get("me/membership/gym-visit", {
        "startDate": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDate": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    if not isinstance(data, list):
        return []
    local = [parse_utc(v["timestamp"]).astimezone(SYDNEY) for v in data]
    local.sort()
    return local


def fetch_nearby(radius_km: int, count: int) -> tuple[dict, list[dict]]:
    gym = home_gym()
    results = api_get("location/search", {
        "latitude": gym["coordinates"]["latitude"],
        "longitude": gym["coordinates"]["longitude"],
        "unitSystem": "Metric",
        "radius": radius_km,
        "page": 1,
        "pageSize": count,
    }) or []
    busy_by_num = {}
    if results:
        numbers = [c["locationNumber"] for c in results]
        params = [("afNumbers", n) for n in numbers]
        url = f"{API_BASE}/clubs/busy-meter?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {get_access_token()}",
            **API_HEADERS_BASE,
        })
        try:
            with urllib.request.urlopen(req) as r:
                busy = json.loads(r.read())
            busy_by_num = {b.get("afNumber"): b for b in busy or []}
        except urllib.error.HTTPError:
            pass
    return gym, [
        {
            "afNumber": c["locationNumber"],
            "name": c["name"],
            "distanceKm": round(c.get("distance", {}).get("value", 0), 1),
            "status": c.get("status", {}).get("description"),
            "isOpen24Hours": c.get("isOpen24Hours"),
            "address": ", ".join(filter(None, [
                c["address"]["address"], c["address"]["city"],
            ])),
            "currentMemberCount": busy_by_num.get(c["locationNumber"], {}).get("currentMemberCount"),
            "isHomeGym": c["locationNumber"] == gym["afNumber"],
        }
        for c in results
    ]


def build_occupancy(af_number: str | None = None) -> dict:
    af_number, name = resolve_club(af_number)
    data = busy_meter(af_number)
    now = datetime.datetime.now()
    usages = find_day_usages(data, now.strftime("%A")) or []
    rest_of_day = [
        {"hour": u["startTime"][:5], "typicalCount": u["averageUsageValue"]}
        for u in usages if int(u["startTime"][:2]) >= now.hour
    ]
    return {
        "afNumber": af_number,
        "name": name,
        "currentMemberCount": data.get("currentMemberCount"),
        "maxAverageUsage": data.get("maxAverageUsage"),
        "busyPercent": (
            round(100 * data["currentMemberCount"] / data["maxAverageUsage"], 1)
            if data.get("currentMemberCount") is not None and data.get("maxAverageUsage")
            else None
        ),
        "restOfDay": rest_of_day,
    }


def build_forecast(day: str, af_number: str | None = None) -> dict:
    af_number, name = resolve_club(af_number)
    data = busy_meter(af_number)
    if day == "today":
        target = datetime.date.today()
    elif day == "tomorrow":
        target = datetime.date.today() + timedelta(days=1)
    else:
        target = None
        for i in range(7):
            d = datetime.date.today() + timedelta(days=i)
            if d.strftime("%A").lower() == day.lower():
                target = d
                break
    if target is None:
        raise SystemExit(f"Unknown day: {day!r} (use 'today', 'tomorrow', or a weekday name)")
    usages = find_day_usages(data, target.strftime("%A")) or []
    return {
        "afNumber": af_number,
        "name": name,
        "date": target.isoformat(),
        "weekday": target.strftime("%A"),
        "hours": [{"hour": u["startTime"][:5], "typicalCount": u["averageUsageValue"]} for u in usages],
    }


def build_recommendation() -> dict:
    af_number, name = resolve_club(None)
    data = busy_meter(af_number)
    now = datetime.datetime.now()
    hour = now.hour
    count = data.get("currentMemberCount")
    if count is None:
        return {"afNumber": af_number, "name": name, "verdict": "no-live-data",
                "message": "This club has no live occupancy right now."}
    typical = None
    for u in find_day_usages(data, now.strftime("%A")) or []:
        if int(u["startTime"][:2]) == hour:
            typical = u["averageUsageValue"]
            break
    if not typical:
        return {"afNumber": af_number, "name": name, "currentMemberCount": count,
                "verdict": "no-baseline", "message": "No typical baseline for this hour."}
    ratio = count / typical
    if ratio <= 0.5:
        verdict = "go-now"
    elif ratio <= 0.85:
        verdict = "good-time"
    elif ratio <= 1.15:
        verdict = "normal"
    elif ratio <= 1.5:
        verdict = "wait"
    else:
        verdict = "skip"
    return {
        "afNumber": af_number, "name": name,
        "timestamp": now.isoformat(timespec="minutes"),
        "currentMemberCount": count,
        "typicalCount": typical,
        "ratio": round(ratio, 2),
        "verdict": verdict,
    }


def build_visit_stats(months: int) -> dict:
    local = fetch_visits(months)
    if not local:
        return {"visits": 0}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    buckets = [(h, h + 2) for h in range(5, 22, 2)]
    grid = {d: {f"{b[0]:02d}": 0 for b in buckets} for d in days}
    for t in local:
        for b in buckets:
            if b[0] <= t.hour < b[1]:
                grid[days[t.weekday()]][f"{b[0]:02d}"] += 1
                break
    dow = Counter(t.strftime("%a") for t in local)
    hour = Counter(t.hour for t in local)
    return {
        "visits": len(local),
        "since": local[0].strftime("%Y-%m-%d"),
        "lastVisit": local[-1].strftime("%Y-%m-%d %H:%M"),
        "mostCommonDay": dow.most_common(1)[0],
        "mostCommonHour": f"{hour.most_common(1)[0][0]:02d}:00",
        "heatmap": grid,
    }


# ------------------------------------------------------------------ cli output
def print_bar_chart(hours: list[dict], title: str):
    print(title)
    for h in hours:
        v = h["typicalCount"]
        print(f"  {h['hour']}  {v:>3}  {'█' * v}")


def cmd_occupancy(args):
    occ = build_occupancy(args.club)
    print(f"{occ['name']} ({occ['afNumber']})")
    if occ["currentMemberCount"] is not None:
        print(f"Now: {occ['currentMemberCount']} people ({occ['busyPercent']}% of typical peak {occ['maxAverageUsage']})")
    else:
        print("No live occupancy for this club. Try `forecast` for typical values.")
    print_bar_chart(occ["restOfDay"], "Rest of today (typical):")


def cmd_forecast(args):
    f = build_forecast(args.day, args.club)
    print_bar_chart(f["hours"], f"{f['weekday']} {f['date']} at {f['name']} ({f['afNumber']}), typical:")


def cmd_nearby(args):
    gym, clubs = fetch_nearby(args.radius, args.limit)
    print(f"Clubs within {args.radius} km of {gym['name']} ({gym['afNumber']}):\n")
    for c in clubs:
        now = f"{c['currentMemberCount']} in now" if c["currentMemberCount"] is not None else "no live data"
        star = " ← home" if c["isHomeGym"] else ""
        print(f"  {c['afNumber']:<8} {c['name']:<28} {c['distanceKm']:>5} km  {c['status']:<9} {now}{star}")
        print(f"           {c['address']}")


def cmd_visits(args):
    stats = build_visit_stats(args.months)
    if not stats.get("visits"):
        print("No visits found.")
        return
    print(f"{stats['visits']} visits since {stats['since']}\n")
    header = "     " + "".join(f"{h:>4}" for h in next(iter(stats["heatmap"].values())))
    print(header)
    for day, row in stats["heatmap"].items():
        max_v = max(row.values()) or 1
        cells = ""
        for v in row.values():
            if v == 0:
                cells += "   ·"
            else:
                blocks = " ▁▂▃▄▅▆▇█"
                cells += f"  {blocks[1 + round(v / max_v * 7)]}"
        print(f" {day}  {cells}")
    print("\nLegend: · none   ▁▂▃ low   ▄▅ mid   ▆▇█ high")
    print(f"\nMost common day: {stats['mostCommonDay'][0]} ({stats['mostCommonDay'][1]} visits)")
    print(f"Most common hour: {stats['mostCommonHour']}")
    print(f"Last visit: {stats['lastVisit']}")


VERDICT_TEXT = {
    "go-now": "Much quieter than usual — GO NOW 🏃",
    "good-time": "Quieter than usual — good time to go",
    "normal": "About normal for this hour",
    "wait": "Busier than usual — maybe wait an hour",
    "skip": "Unusually packed — skip it if you can",
}


def cmd_when(_args):
    r = build_recommendation()
    print(f"{r['name']} ({r['afNumber']}), {datetime.datetime.now().strftime('%a %H:%M')}")
    if r.get("verdict") in ("no-live-data", "no-baseline"):
        print(r["message"])
        return
    pct = round((r["ratio"] - 1) * 100)
    diff = f"{abs(pct)}% {'busier' if pct > 0 else 'quieter'} than usual" if pct else "exactly typical"
    print(f"Now: {r['currentMemberCount']} people (typical: {r['typicalCount']}) — {diff}.")
    print(VERDICT_TEXT[r["verdict"]])


# ------------------------------------------------------------------ serve
def cmd_serve(args):
    try:
        import uvicorn
        from fastapi import FastAPI, HTTPException, Query
    except ImportError:
        raise SystemExit(
            "Serving needs FastAPI. Run with uv (auto-installs deps):\n"
            "  uv run af_api.py serve"
        )

    app = FastAPI(
        title="Anytime Fitness Occupancy API",
        description="Personal gym occupancy service backed by the AF App 4.5.0 mobile API "
                    "(unofficial). Read-only, personal use.",
        version="1.0.0",
    )

    def guard(fn):
        try:
            return fn()
        except SystemExit as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "tokenPresent": TOKEN_FILE.exists()}

    @app.get("/api/v1/profile")
    def profile():
        return guard(lambda: api_get("me/user"))

    @app.get("/api/v1/gym")
    def gym():
        return guard(lambda: home_gym())

    @app.get("/api/v1/occupancy")
    def occupancy(club: str | None = None):
        return guard(lambda: build_occupancy(club))

    @app.get("/api/v1/forecast")
    def forecast(day: str = Query("tomorrow", description="today, tomorrow, or weekday name"),
                 club: str | None = None):
        return guard(lambda: build_forecast(day, club))

    @app.get("/api/v1/clubs/nearby")
    def nearby(radius: int = 25, limit: int = 5):
        return guard(lambda: fetch_nearby(radius, limit)[1])

    @app.get("/api/v1/visits")
    def visits(months: int = 12):
        return guard(lambda: build_visit_stats(months))

    @app.get("/api/v1/recommendation")
    def recommendation():
        return guard(build_recommendation)

    print(f"Serving on http://127.0.0.1:{args.port}  (Swagger docs: http://127.0.0.1:{args.port}/docs)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


# ------------------------------------------------------------------ main
def main():
    parser = argparse.ArgumentParser(
        prog="af_api",
        description="Anytime Fitness gym occupancy client (unofficial). "
                    "Personal use only.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="request an SMS login code")
    p.add_argument("--phone", required=True, help="phone in E.164 format, e.g. +61400000000")

    p = sub.add_parser("verify", help="verify SMS code and save auth token")
    p.add_argument("--code", required=True)

    sub.add_parser("profile", help="show account details")
    sub.add_parser("gym", help="show home gym details")

    p = sub.add_parser("occupancy", help="live headcount + rest-of-day forecast")
    p.add_argument("club", nargs="?", help="club af-number (default: home gym)")

    p = sub.add_parser("forecast", help="typical hourly pattern for a day")
    p.add_argument("club", nargs="?", help="club af-number (default: home gym)")
    p.add_argument("--day", default="tomorrow",
                   help="'today', 'tomorrow', or a weekday name (default: tomorrow)")

    p = sub.add_parser("nearby", help="clubs around your home gym with live counts")
    p.add_argument("--radius", type=int, default=25, help="search radius in km (default 25)")
    p.add_argument("--limit", type=int, default=5, help="max clubs (default 5)")

    p = sub.add_parser("visits", help="your visit history with heatmap")
    p.add_argument("--months", type=int, default=12, help="lookback months (default 12)")

    sub.add_parser("when", help="go-now verdict: live count vs typical for this hour")

    p = sub.add_parser("serve", help="expose as a REST API (Swagger at /docs)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")

    args = parser.parse_args()

    if args.command == "login":
        request_sms_code(args.phone)
    elif args.command == "verify":
        verify_sms_code(args.code)
    elif args.command == "profile":
        print(json.dumps(api_get("me/user"), indent=2))
    elif args.command == "gym":
        print(json.dumps(home_gym(), indent=2))
    elif args.command == "occupancy":
        cmd_occupancy(args)
    elif args.command == "forecast":
        cmd_forecast(args)
    elif args.command == "nearby":
        cmd_nearby(args)
    elif args.command == "visits":
        cmd_visits(args)
    elif args.command == "when":
        cmd_when(args)
    elif args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
