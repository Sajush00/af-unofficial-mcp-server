"""Cognito SMS login and the token lifecycle.

Auth state lives in two JSON files under the home directory:
- the token file (~/.af_token.json) holds access and refresh tokens;
- the session file (~/.af_session.json) holds an in-flight SMS challenge.

AF_TOKEN_FILE and AF_SESSION_FILE override both paths, which is also how the
tests keep state out of the real home directory.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from af_mcp import http, timeutil
from af_mcp.errors import AFError, LoginRequiredError

COGNITO_URL = "https://cognito-idp.us-east-1.amazonaws.com/"
COGNITO_CLIENT_ID = "r56fk5c6c5gfaegh5j673hdeq"

LOGIN_HINT = (
    "No usable Anytime Fitness session. Run: af-gym login --phone <number>, "
    "then af-gym verify --code <code>."
)


def default_token_file() -> Path:
    """Token file path: AF_TOKEN_FILE, else ~/.af_token.json."""
    override = os.environ.get("AF_TOKEN_FILE")
    return Path(override) if override else Path.home() / ".af_token.json"


def default_session_file() -> Path:
    """Session file path: AF_SESSION_FILE, else ~/.af_session.json."""
    override = os.environ.get("AF_SESSION_FILE")
    return Path(override) if override else Path.home() / ".af_session.json"


class Authenticator:
    """Cognito flows for one account, over the shared HTTP seam."""

    def __init__(self, *, token_file: Path | None = None, session_file: Path | None = None) -> None:
        self.token_file = token_file or default_token_file()
        self.session_file = session_file or default_session_file()

    def request_sms_code(self, phone: str) -> None:
        """Start an SMS login; the code is texted to the registered number."""
        response = self._cognito(
            "InitiateAuth",
            {
                "AuthFlow": "USER_AUTH",
                "AuthParameters": {"USERNAME": phone, "PREFERRED_CHALLENGE": "SMS_OTP"},
                "ClientId": COGNITO_CLIENT_ID,
                "ClientMetadata": {"deliveryChannel": "sms"},
            },
        )
        session = response.get("Session")
        if not session:
            raise LoginRequiredError(
                f"Cognito did not start an SMS challenge: {json.dumps(response)[:200]}"
            )
        self.session_file.write_text(
            json.dumps(
                {
                    "phone": phone,
                    "session": session,
                    "challenge": response.get("ChallengeName", "SMS_OTP"),
                }
            )
        )

    def verify_sms_code(self, code: str) -> None:
        """Complete an in-flight SMS login and persist the tokens."""
        if not self.session_file.exists():
            raise LoginRequiredError("No in-flight login. Run: af-gym login --phone <number>")
        state = json.loads(self.session_file.read_text())
        response = self._cognito(
            "RespondToAuthChallenge",
            {
                "ChallengeName": state.get("challenge", "SMS_OTP"),
                "ClientId": COGNITO_CLIENT_ID,
                "Session": state["session"],
                "ChallengeResponses": {"USERNAME": state["phone"], "SMS_OTP_CODE": code},
            },
        )
        result = response.get("AuthenticationResult")
        if not result:
            raise LoginRequiredError(f"SMS verification failed: {json.dumps(response)[:200]}")
        self._store(result)
        self.session_file.unlink(missing_ok=True)

    def access_token(self) -> str:
        """Return a valid access token, refreshing it close to expiry."""
        stored = self._load()
        if stored is None:
            raise LoginRequiredError(LOGIN_HINT)
        if time.time() > float(stored.get("expires_at", 0)) - 60:
            stored = self._refresh(stored)
        return str(stored["AccessToken"])

    def status(self) -> dict[str, Any]:
        """Describe the saved session without returning any token values."""
        try:
            self.access_token()
        except LoginRequiredError as exc:
            return {"loggedIn": False, "detail": str(exc)}
        stored = self._load() or {}
        expires_at = stored.get("expires_at")
        return {
            "loggedIn": True,
            "accessTokenExpires": (
                timeutil.moment_string(
                    datetime.fromtimestamp(float(expires_at), tz=timeutil.club_zone())
                )
                if expires_at
                else None
            ),
            "autoRefresh": bool(stored.get("RefreshToken")),
        }

    # ------------------------------------------------------------- internals
    def _cognito(self, operation: str, body: dict[str, Any]) -> dict[str, Any]:
        response = http.request_json(
            COGNITO_URL,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": f"AWSCognitoIdentityProviderService.{operation}",
            },
            body=json.dumps(body).encode(),
            method="POST",
        )
        if not isinstance(response, dict):
            raise AFError("Cognito returned an unexpected response shape.")
        return response

    def _load(self) -> dict[str, Any] | None:
        if not self.token_file.exists():
            return None
        try:
            loaded = json.loads(self.token_file.read_text())
        except ValueError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def _store(self, result: dict[str, Any]) -> dict[str, Any]:
        stored = {
            "AccessToken": result["AccessToken"],
            "RefreshToken": result.get("RefreshToken"),
            "expires_at": time.time() + float(result.get("ExpiresIn", 3600)),
        }
        self.token_file.write_text(json.dumps(stored))
        return stored

    def _refresh(self, stored: dict[str, Any]) -> dict[str, Any]:
        refresh_token = stored.get("RefreshToken")
        if not refresh_token:
            raise LoginRequiredError(LOGIN_HINT)
        response = self._cognito(
            "GetTokensFromRefreshToken",
            {
                "RefreshToken": refresh_token,
                "ClientId": COGNITO_CLIENT_ID,
            },
        )
        result = response.get("AuthenticationResult")
        if not result:
            raise LoginRequiredError(
                "Refresh token expired. Log in again: af-gym login --phone <number>"
            )
        # Refresh tokens are not rotated; keep the existing one when the
        # response does not carry a new one.
        result.setdefault("RefreshToken", refresh_token)
        return self._store(result)


# ---------------------------------------------------------------- convenience
def request_sms_code(phone: str) -> None:
    """Request an SMS login code for the default session file."""
    Authenticator().request_sms_code(phone)


def verify_sms_code(code: str) -> None:
    """Complete the SMS login for the default session file."""
    Authenticator().verify_sms_code(code)


def access_token() -> str:
    """Return a valid access token for the default token file."""
    return Authenticator().access_token()


def status() -> dict[str, Any]:
    """Describe the saved session without returning token values."""
    return Authenticator().status()
