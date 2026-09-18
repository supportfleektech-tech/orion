#!/usr/bin/env bash
set -euo pipefail
if [ $# -ne 1 ]; then echo "Usage: $0 /absolute/path/to/file"; exit 2; fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
export PYTHONPATH="$ROOT/backend"
python - <<PY
import asyncio
from app.db.database import SessionLocal
from app.services.ingestion import ingest_path

async def main():
    db=SessionLocal()
    try:
        print(await ingest_path(db, "$1"))
    finally:
        db.close()

asyncio.run(main())
PY
