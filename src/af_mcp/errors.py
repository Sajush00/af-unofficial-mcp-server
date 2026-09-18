"""Exception hierarchy for the AF client.

Every failure the package raises is an AFError subclass, so adapters (the MCP
server, the CLI) translate errors by category instead of matching message
strings. Static checks keep the discipline in place: AF008 bans builtin
exceptions (RuntimeError, ValueError, ...) in src, and AF001 bans process
exits outside __main__ guards.
"""

from __future__ import annotations


class AFError(Exception):
    """Base class for every failure raised by this package."""


class LoginRequiredError(AFError):
    """No usable session; the SMS login flow has to run."""


class InvalidInputError(AFError):
    """A caller-supplied value cannot be used (bad date, unknown day, ...)."""


class TransportError(AFError):
    """The request never produced an HTTP response (DNS, timeout, refused)."""


class ApiError(AFError):
    """The AF API answered with an error status."""

    def __init__(self, status: int, detail: str, path: str) -> None:
        super().__init__(f"HTTP {status} for {path}: {detail}")
        self.status = status
        self.detail = detail
        self.path = path
