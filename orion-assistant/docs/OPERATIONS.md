# Operations

## Deploy

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:8000/health
```

UI on `:8080`, API on `:8000`. The `api` service has a healthcheck and `web` waits for it.

### Persistence

| Volume | Contents |
|---|---|
| `orion-data` | SQLite database (`/data/orion.db`) |
| `orion-knowledge` | Uploaded and ingested source files |

Back up with `docker run --rm -v orion_orion-data:/d -v $PWD:/b alpine tar czf /b/orion-data.tgz /d`.

### Postgres

```bash
docker compose --profile postgres up -d postgres
# in .env:
DATABASE_URL=postgresql+psycopg://orion:orion@postgres:5432/orion
docker compose up -d --build api
```

Tables are created automatically at boot.

## Monitor

| Endpoint | Use |
|---|---|
| `GET /health` | Liveness / readiness probe |
| `GET /v1/system/status` | Provider reachability, counts, flags, kill switch |
| `GET /v1/system/metrics` | Success rates, latency, router statistics |
| `GET /v1/audit` | Governance event stream |

The Command Center and Observability pages surface all of these.

## Upgrade

```bash
git pull
docker compose up -d --build
```

Schema changes are additive and applied by `init_db()`. For destructive schema changes, back up
first and introduce Alembic.

## Tuning behaviour

The live system prompt is `backend/app/prompts/system.md`. Edit it and restart the API to change how
ORION behaves — no code change required. It ships inside the image, so when using Docker either
rebuild or bind-mount the file.

Runtime flags changed via the Settings page or `PATCH /v1/settings` are persisted to the `settings`
table and re-applied on boot (look for `Applied N persisted setting override(s)` in the log).
Secrets, bind addresses and `DATABASE_URL` are deliberately **not** runtime-mutable; they come from
the environment only.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Retrieval-only answer" banner | No model backend reachable | Start Ollama or set `OPENROUTER_API_KEY` |
| Embedding warning in logs | Ollama embed model missing | `ollama pull nomic-embed-text` (hashed fallback is in use meanwhile) |
| Tool shows "blocked" | Capability flag off or kill switch on | Toggle in Settings / Security |
| `429` responses | Rate limit hit | Raise `RATE_LIMIT_PER_MINUTE` |
| Container cannot reach Ollama | Host networking | Use `http://host.docker.internal:11434/v1` (already configured) |

## Runbook: agent behaving unexpectedly

1. Engage the kill switch (Security page).
2. Inspect the run trace in Observability and the audit log.
3. Disable the offending tool in Settings or Tools.
4. Delete bad memories in the Memory page.
5. Release the kill switch.
