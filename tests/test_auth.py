"""Tests for the auth lifecycle: SMS login, token refresh, status."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from af_mcp import auth
from af_mcp.errors import LoginRequiredError, TransportError
from factories import read_token, write_token

COGNITO = "cognito-idp"


def test_access_token_uses_stored_token_without_refreshing(fake_api, auth_env: Path):
    assert auth.access_token() == "test-access"
    assert fake_api.calls == []


def test_missing_token_file_requires_login(fake_api, auth_env: Path):
    (auth_env / "token.json").unlink()
    with pytest.raises(LoginRequiredError, match="login"):
        auth.access_token()


def test_expired_token_refreshes_and_keeps_the_refresh_token(fake_api, auth_env: Path):
    write_token(auth_env, expires_in=-10)
    fake_api.route(
        COGNITO,
        {
            "AuthenticationResult": {"AccessToken": "fresh-access", "ExpiresIn": 86400},
        },
    )
    assert auth.access_token() == "fresh-access"
    stored = read_token(auth_env)
    assert stored["AccessToken"] == "fresh-access"
    # The API does not rotate refresh tokens; the old one must survive.
    assert stored["RefreshToken"] == "test-refresh"
    assert stored["expires_at"] > time.time()


def test_expired_token_with_new_refresh_token_uses_it(fake_api, auth_env: Path):
    write_token(auth_env, expires_in=-10)
    fake_api.route(
        COGNITO,
        {
            "AuthenticationResult": {
                "AccessToken": "fresh",
                "RefreshToken": "rotated",
                "ExpiresIn": 86400,
            },
        },
    )
    auth.access_token()
    assert read_token(auth_env)["RefreshToken"] == "rotated"


def test_refresh_failure_requires_login(fake_api, auth_env: Path):
    write_token(auth_env, expires_in=-10)
    fake_api.route(COGNITO, {"message": "refresh token expired"})
    with pytest.raises(LoginRequiredError, match=r"login|expired"):
        auth.access_token()


def test_token_without_refresh_token_requires_login(fake_api, auth_env: Path):
    write_token(auth_env, refresh=None, expires_in=-10)
    with pytest.raises(LoginRequiredError):
        auth.access_token()


def test_corrupt_token_file_requires_login(fake_api, auth_env: Path):
    (auth_env / "token.json").write_text("{not json")
    with pytest.raises(LoginRequiredError):
        auth.access_token()


def test_request_sms_code_stores_the_session(fake_api, auth_env: Path):
    fake_api.route(COGNITO, {"Session": "session-123", "ChallengeName": "SMS_OTP"})
    auth.request_sms_code("+61400000000")
    state = json.loads((auth_env / "session.json").read_text())
    assert state["phone"] == "+61400000000"
    assert state["session"] == "session-123"


def test_request_sms_code_without_session_is_an_error(fake_api, auth_env: Path):
    fake_api.route(COGNITO, {"oops": True})
    with pytest.raises(LoginRequiredError):
        auth.request_sms_code("+61400000000")


def test_verify_sms_code_saves_tokens_and_clears_the_session(fake_api, auth_env: Path):
    (auth_env / "session.json").write_text(
        json.dumps(
            {
                "phone": "+61400000000",
                "session": "session-123",
                "challenge": "SMS_OTP",
            }
        )
    )
    fake_api.route(
        COGNITO,
        {
            "AuthenticationResult": {
                "AccessToken": "sms-access",
                "RefreshToken": "sms-refresh",
                "ExpiresIn": 3600,
            },
        },
    )
    auth.verify_sms_code("123456")
    assert read_token(auth_env)["AccessToken"] == "sms-access"
    assert not (auth_env / "session.json").exists()


def test_verify_without_pending_login_requires_login(fake_api, auth_env: Path):
    with pytest.raises(LoginRequiredError, match="login"):
        auth.verify_sms_code("123456")


def test_verify_rejection_keeps_the_session_removed_only_on_success(fake_api, auth_env: Path):
    (auth_env / "session.json").write_text(
        json.dumps(
            {
                "phone": "+61400000000",
                "session": "session-123",
                "challenge": "SMS_OTP",
            }
        )
    )
    fake_api.route(COGNITO, {"message": "invalid code"})
    with pytest.raises(LoginRequiredError):
        auth.verify_sms_code("000000")
    assert (auth_env / "session.json").exists()


def test_status_reports_session_metadata_without_token_values(fake_api, auth_env: Path):
    status = auth.status()
    assert status["loggedIn"] is True
    assert status["autoRefresh"] is True
    assert "test-access" not in json.dumps(status)


def test_status_without_session(fake_api, auth_env: Path):
    (auth_env / "token.json").unlink()
    status = auth.status()
    assert status["loggedIn"] is False
    assert "login" in status["detail"].lower()


def test_logout_revokes_and_deletes_local_state(fake_api, auth_env: Path):
    fake_api.route(COGNITO, None)  # RevokeToken replies with an empty body
    result = auth.logout()
    assert result == {"hadSession": True, "revoked": True}
    assert not (auth_env / "token.json").exists()
    targets = [call["headers"].get("X-Amz-Target", "") for call in fake_api.calls]
    assert targets == ["AWSCognitoIdentityProviderService.RevokeToken"]


def test_logout_without_refresh_token_stays_local(fake_api, auth_env: Path):
    write_token(auth_env, refresh=None)
    result = auth.logout()
    assert result == {"hadSession": True, "revoked": False}
    assert fake_api.calls == []
    assert not (auth_env / "token.json").exists()


def test_logout_without_a_session_is_a_no_op(fake_api, auth_env: Path):
    (auth_env / "token.json").unlink()
    result = auth.logout()
    assert result == {"hadSession": False, "revoked": False}
    assert fake_api.calls == []


def test_logout_survives_a_failed_revoke(fake_api, auth_env: Path):
    fake_api.route(COGNITO, TransportError("offline"))
    result = auth.logout()
    assert result == {"hadSession": True, "revoked": False}
    assert not (auth_env / "token.json").exists()
