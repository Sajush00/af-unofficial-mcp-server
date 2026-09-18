# ADR 0001: one HTTP seam

## Context

The first version of the client performed `urllib` calls from several
modules (the API transport, an ad-hoc batch request inside `fetch_nearby`,
and the Cognito calls in auth). Tests had no single place to intercept the
network, so the suite either hit the live API or mocked several call sites.

## Decision

All outbound HTTP goes through `af_mcp/http.py`. `request_json()` is the
only function in the package that calls `urlopen()`. Every other module
goes through `transport.api_get()`, which adds the auth header and version
headers.

The rule is enforced by static check AF004 (no `urllib` imports outside
`http.py`) and by the test fixture that replaces `http.request_json` with a
fake.

## Consequences

- One place to fake in tests, one place to add timeouts, retries, or logging.
- New endpoints cannot quietly bypass the auth header.
- `http.py` carries the only `# noqa: S310` in the codebase, with the reason
  next to it.
