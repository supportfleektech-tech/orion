# Security

## Threat model

ORION is a single-user, local-first assistant that can read files, reach the network and execute
commands. The main risks are prompt injection causing unwanted tool use, data exfiltration and
accidental destructive actions.

## Controls

### 1. Capability flags (deny by default)

`ENABLE_WEB_SEARCH`, `ALLOW_NETWORK_TOOL`, `ALLOW_SHELL_TOOL`, `ALLOW_BROWSER_TOOL` are all `false`
in `.env.example`. Disabled tools are not even advertised to the model.

### 2. Risk tiers and approvals

| Tier | Behaviour |
|---|---|
| `low` | Executes automatically |
| `medium` | Executes if its category flag is enabled |
| `high` | Creates a pending approval request |
| `destructive` | Creates a pending approval request |

Approvals are resolved from the Security page or `POST /v1/approvals/{id}`. Rejected requests never
execute.

### 3. Kill switch

`POST /v1/security/kill-switch` blocks every tool immediately, regardless of tier or flag. The agent
can still answer from memory and knowledge.

### 4. Sandboxing

* File tools are confined to `KNOWLEDGE_DIR`; path traversal is rejected by resolved-path checks.
* Shell commands run in that directory, are argument-parsed (no shell interpolation), deny a list of
  dangerous binaries and are killed after `SHELL_TIMEOUT_SECONDS`.
* HTTP requests are limited to http/https and, when `HTTP_ALLOWLIST` is set, to those hosts only.
* The arithmetic tool uses an AST allowlist — no `eval`, no names, bounded exponents.

### 5. Transport and access

* `AUTH_ENABLED=true` requires `Authorization: Bearer <ADMIN_TOKEN>` on every mutating endpoint.
* Per-IP rate limiting (`RATE_LIMIT_PER_MINUTE`).
* Restrict `CORS_ORIGINS` in production; nginx sets `X-Content-Type-Options`, `X-Frame-Options` and
  `Referrer-Policy`.
* Run behind TLS. The container runs as a non-root user (uid 10001).

### 6. Audit

Every tool execution, denial, approval decision, settings change and kill-switch toggle is written
to `audit_events` and shown in the Security page.

## Prompt injection guidance

Retrieved memory and documents are injected as *context*, and the system prompt instructs the model
to treat them as untrusted evidence rather than instructions. Because instruction-following can
still be subverted, the real defence is the policy gate: injected text cannot execute a high-risk
tool without a human approval click.

## Reporting

Do not open a public issue for vulnerabilities. Contact the maintainer directly.


## Hardening notes

Two things that matter only once ORION is reachable beyond localhost, both
fixed and covered by tests in `backend/tests/test_auth.py`:

**Rate-limit state is bounded.** Buckets are keyed by client address and swept
every 500 requests, dropping any client not seen inside the 60s window.
Without the sweep the map grew by one entry per distinct address forever —
measured at ~16MB for 20,000 addresses — which an attacker can drive simply by
varying the source address.

**The admin token is compared with `secrets.compare_digest`.** A plain `!=`
short-circuits on the first differing byte, leaking the shared prefix length
through response timing, which is enough to recover a token byte by byte. An
unset `ADMIN_TOKEN` also never authorises an empty bearer header.

### Before exposing ORION to a network

The defaults assume a single user on their own machine:

* `AUTH_ENABLED=false` — turn it on and set `ADMIN_TOKEN`.
* `CORS_ORIGINS=*` — narrow it to the origin you actually serve.
* `RATE_LIMIT_PER_MINUTE` applies per client address; behind a reverse proxy
  every request appears to come from the proxy unless it forwards the real
  address.
