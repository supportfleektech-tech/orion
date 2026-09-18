# Observability

## What is recorded

| Signal | Table | Surfaced in |
|---|---|---|
| Agent runs and traces | `agent_runs` | Observability page, `/v1/runs` |
| Tool executions | `tool_runs` | Tools page, `/v1/tools/runs` |
| Governance events | `audit_events` | Security page, `/v1/audit` |
| Router statistics | in-memory | Command Center, `/v1/system/metrics` |
| Message latency | `messages.latency_ms` | Conversation metadata |

## Metrics

`GET /v1/system/metrics` returns agent success rate, tool success rate, average run duration, router
call counts by provider, failure and degraded-call counts, and a recent run timeline.

## Traces

`GET /v1/runs/{id}` returns the ordered trace: per-iteration provider, model, latency and requested
tool calls, plus per-tool arguments and outcome. The Observability page renders this in a modal.

## Logs

Structured to stdout at `LOG_LEVEL`. Notable lines: model attempt failures (provider, model, error),
the one-time embedding fallback warning, scheduler activity and unhandled request errors. Every HTTP
response carries `X-Process-Time-Ms` and `X-Orion-Version`.

## Health probes

* Liveness: `GET /health`
* Readiness with dependency detail: `GET /v1/system/status` — the `degraded` boolean is true when no
  model provider is reachable.

Both Docker services declare healthchecks; `web` starts only after `api` is healthy.
