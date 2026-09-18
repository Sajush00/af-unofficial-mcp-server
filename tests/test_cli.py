"""Tests for the auth-only CLI: surface, login flow, status, logout."""

from __future__ import annotations

from pathlib import Path

import pytest

from af_mcp import cli
from factories import read_token

COGNITO = "cognito-idp"
PHONE = "+61400000000"


def cognito(url: str, headers: dict, body: bytes | None) -> dict | None:
    """Dispatch the CLI's Cognito calls for a full login (and revoke)."""
    target = headers.get("X-Amz-Target", "")
    if target.endswith("InitiateAuth"):
        return {"Session": "cli-session", "ChallengeName": "SMS_OTP"}
    if target.endswith("RespondToAuthChallenge"):
        return {
            "AuthenticationResult": {
                "AccessToken": "cli-access",
                "RefreshToken": "cli-refresh",
                "ExpiresIn": 3600,
            }
        }
    if target.endswith("RevokeToken"):
        return None
    raise AssertionError(f"unexpected Cognito call: {target}")


def test_auth_commands_parse():
    parser = cli.build_parser()
    assert parser.parse_args(["login", "--phone", PHONE]).func is cli.cmd_login
    assert parser.parse_args(["status"]).func is cli.cmd_status
    assert parser.parse_args(["logout"]).func is cli.cmd_logout


def test_query_commands_are_gone():
    parser = cli.build_parser()
    for command in (
        "occupancy",
        "forecast",
        "nearby",
        "visits",
        "when",
        "profile",
        "gym",
        "verify",
    ):
        with pytest.raises(SystemExit):
            parser.parse_args([command])


def test_login_with_code_flag_saves_the_session(fake_api, auth_env: Path, capsys):
    fake_api.route(COGNITO, cognito)
    assert cli.main(["login", "--phone", PHONE, "--code", "123456"]) == 0
    assert read_token(auth_env)["AccessToken"] == "cli-access"
    assert "Logged in" in capsys.readouterr().out


def test_login_prompts_for_the_code(fake_api, auth_env: Path, monkeypatch, capsys):
    fake_api.route(COGNITO, cognito)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "123456")
    assert cli.main(["login", "--phone", PHONE]) == 0
    assert read_token(auth_env)["AccessToken"] == "cli-access"


def test_login_without_input_fails_with_a_rerun_hint(fake_api, auth_env: Path, monkeypatch, capsys):
    fake_api.route(COGNITO, cognito)

    def no_input(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_input)
    assert cli.main(["login", "--phone", PHONE]) == 1
    assert "--code" in capsys.readouterr().err


def test_login_af_errors_become_a_clean_stderr_message(fake_api, auth_env: Path, capsys):
    fake_api.route(COGNITO, {"oops": True})
    assert cli.main(["login", "--phone", PHONE, "--code", "123456"]) == 1
    assert "error:" in capsys.readouterr().err


def test_status_reports_a_logged_in_session(fake_api, auth_env: Path, capsys):
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Logged in" in out and "expires" in out


def test_status_reports_a_missing_session(fake_api, auth_env: Path, capsys):
    (auth_env / "token.json").unlink()
    assert cli.main(["status"]) == 0
    assert "af-gym login" in capsys.readouterr().out


def test_logout_revokes_and_deletes_local_tokens(fake_api, auth_env: Path, capsys):
    fake_api.route(COGNITO, cognito)
    assert cli.main(["logout"]) == 0
    assert "Logged out" in capsys.readouterr().out
    assert not (auth_env / "token.json").exists()
    targets = [call["headers"].get("X-Amz-Target", "") for call in fake_api.calls]
    assert any(target.endswith("RevokeToken") for target in targets)


def test_logout_without_a_session_says_so(fake_api, auth_env: Path, capsys):
    (auth_env / "token.json").unlink()
    assert cli.main(["logout"]) == 0
    assert "No saved session" in capsys.readouterr().out
