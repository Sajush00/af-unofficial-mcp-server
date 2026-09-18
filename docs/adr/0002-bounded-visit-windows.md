# ADR 0002: bounded visit windows

## Context

The gym-visit endpoint accepts dates back to account creation, so a fetch
without bounds returns the whole history. An early version of the visit
tool pulled everything and sliced client-side. That grows agent context for
no benefit and got a direct complaint: "it makes no sense to not be able to
filter and have to pull all the visits each time".

## Decision

`visits.fetch_window(start, end)` always sends `startDate` and `endDate`.
Tool-facing `visit_history` defaults to the last 90 days, lists a capped
number of rows (with `totalInRange` and `truncated` alongside), and widens
once to 730 days only to find the most recent visit when the default window
is empty.

The rule is enforced by static check AF005: any occurrence of the endpoint
string must sit inside a call that passes both bounds.

## Consequences

- Small payloads by default; a caller asks for more with `start`/`end`.
- "How many visits in August" costs one narrow request and returns a count,
  not a list.
- The widen branch keeps "when did I last go?" answerable without pulling
  everything.
