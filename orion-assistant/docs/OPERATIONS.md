# Operations Runbook

## Start

```bash
./scripts/bootstrap.sh
./scripts/run-backend.sh
./scripts/run-frontend.sh
```

## Health

```bash
./scripts/healthcheck.sh
```

## Backups

```bash
docker compose exec postgres pg_dump -U orion -d orion > backup.sql
```

Encrypt off-device backups.

## Upgrade strategy

1. backup database;
2. pin application dependency versions in release builds;
3. run migration tests;
4. run golden evaluation suite;
5. upgrade one component at a time.

## Disaster recovery

The minimum recoverable state is:

- Postgres dump;
- `.env` secrets stored separately;
- knowledge source files;
- connector configuration metadata;
- prompt/policy versions;
- evaluation suite.

## Local-only emergency mode

Set:

```env
LOCAL_ONLY=true
CLOUD_ESCALATION_ENABLED=false
ENABLE_WEB_SEARCH=false
ALLOW_SHELL_TOOL=false
ALLOW_BROWSER_TOOL=false
ALLOW_NETWORK_TOOL=false
```

Then restart the API.
