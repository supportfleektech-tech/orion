"""Alembic migrations: the schema on disk must match the models in code."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parent.parent
BASELINE = "3fce4a4a6ed7"  # first revision; legacy databases match this schema
MODEL_TABLES = {
    "conversations", "messages", "memories", "documents", "chunks",
    "tool_runs", "agent_runs", "approvals", "automations", "settings",
    "audit_events", "skills", "feedback",
}


def alembic(*args: str, db_url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": db_url, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{tmp_path}/migrate.db"


def test_upgrade_creates_every_model_table(db_url, tmp_path):
    result = alembic("upgrade", "head", db_url=db_url)
    assert result.returncode == 0, result.stderr

    tables = set(inspect(create_engine(db_url)).get_table_names())
    missing = MODEL_TABLES - tables
    assert not missing, f"migration did not create: {sorted(missing)}"
    assert "alembic_version" in tables


def test_downgrade_removes_everything(db_url):
    assert alembic("upgrade", "head", db_url=db_url).returncode == 0
    result = alembic("downgrade", "base", db_url=db_url)
    assert result.returncode == 0, result.stderr

    tables = set(inspect(create_engine(db_url)).get_table_names())
    assert not (MODEL_TABLES & tables), "downgrade left tables behind"


def test_upgrade_is_idempotent(db_url):
    assert alembic("upgrade", "head", db_url=db_url).returncode == 0
    second = alembic("upgrade", "head", db_url=db_url)
    assert second.returncode == 0, second.stderr


def test_no_model_drift(db_url):
    """Autogenerate must find nothing new after upgrading.

    This is the test that actually earns its keep: if someone adds a column to
    a model and forgets the migration, this fails.
    """
    assert alembic("upgrade", "head", db_url=db_url).returncode == 0
    result = alembic(
        "revision", "--autogenerate", "-m", "drift-check", "--sql", db_url=db_url
    )
    # --sql with autogenerate is rejected by alembic; do it via check instead.
    result = alembic("check", db_url=db_url)
    assert result.returncode == 0, (
        "Models have drifted from migrations. Run "
        "`./scripts/migrate.sh new \"describe change\"` and commit the revision.\n"
        f"{result.stdout}\n{result.stderr}"
    )


# ------------------------------------------------------------------ runtime
def test_migration_status_reports_up_to_date():
    from app.db.database import migration_status

    status = migration_status()
    assert status["error"] is None
    assert status["current_revision"] is not None
    assert status["up_to_date"] is True, "test database should be stamped at head"


def test_health_endpoint_exposes_schema_state(client):
    schema = client.get("/health").json()["schema"]
    assert schema["up_to_date"] is True
    assert schema["head_revision"]


def test_env_uses_settings_url_not_the_ini(monkeypatch):
    """DATABASE_URL is the single source of truth; the ini must not override it."""
    from app.core.config import settings
    from app.db.database import alembic_config

    monkeypatch.setattr(settings, "database_url", "sqlite:///./sentinel-check.db")
    assert alembic_config().get_main_option("sqlalchemy.url") == "sqlite:///./sentinel-check.db"


def test_create_all_then_stamp_is_a_valid_baseline(tmp_path):
    """A zero-config SQLite start must still be a valid migration baseline.

    init_db() does create_all + stamp; after that, `alembic upgrade head` should
    be a no-op rather than trying to recreate existing tables.
    """
    db_url = f"sqlite:///{tmp_path}/fresh.db"
    from app.db.models import Base

    Base.metadata.create_all(bind=create_engine(db_url))

    assert alembic("stamp", "head", db_url=db_url).returncode == 0
    result = alembic("upgrade", "head", db_url=db_url)
    assert result.returncode == 0, result.stderr

    tables = set(inspect(create_engine(db_url)).get_table_names())
    assert MODEL_TABLES <= tables


# --------------------------------------------------- upgrade-on-boot behaviour
def test_init_db_upgrades_a_legacy_database(tmp_path, monkeypatch):
    """A database from before a migration must be brought forward on boot.

    This is the regression test for the bug where init_db only stamped and
    never upgraded, leaving running deployments with a schema missing the
    columns the code expected.
    """
    import sqlalchemy

    from app.core.config import settings
    from app.db import database as db_module

    db_file = tmp_path / "legacy.db"
    db_url = f"sqlite:///{db_file}"

    # Build a database at the baseline revision, then strip Alembic's bookkeeping
    # so it looks like a pre-migrations deployment.
    assert alembic("upgrade", BASELINE, db_url=db_url).returncode == 0
    legacy_engine = sqlalchemy.create_engine(db_url)
    with legacy_engine.begin() as connection:
        connection.execute(sqlalchemy.text("DROP TABLE alembic_version"))
    legacy_engine.dispose()

    columns = {c["name"] for c in inspect(sqlalchemy.create_engine(db_url)).get_columns("conversations")}
    assert "persona" not in columns, "fixture should start without the newer column"

    # Point the module at the legacy database and boot.
    engine = sqlalchemy.create_engine(db_url)
    monkeypatch.setattr(settings, "database_url", db_url)
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.init_db()

    columns = {c["name"] for c in inspect(engine).get_columns("conversations")}
    assert "persona" in columns, "init_db did not apply the pending migration"
    assert db_module.current_revision() == db_module.head_revision()


def test_init_db_on_a_fresh_database_stamps_head(tmp_path, monkeypatch):
    import sqlalchemy

    from app.core.config import settings
    from app.db import database as db_module

    db_url = f"sqlite:///{tmp_path}/brand-new.db"
    engine = sqlalchemy.create_engine(db_url)
    monkeypatch.setattr(settings, "database_url", db_url)
    monkeypatch.setattr(db_module, "engine", engine)

    db_module.init_db()

    assert MODEL_TABLES <= set(inspect(engine).get_table_names())
    assert db_module.current_revision() == db_module.head_revision()


def test_init_db_survives_a_broken_migration(tmp_path, monkeypatch):
    """A failing migration must be logged, not crash the process on boot."""
    import sqlalchemy

    from app.core.config import settings
    from app.db import database as db_module

    db_url = f"sqlite:///{tmp_path}/broken.db"
    assert alembic("upgrade", "head", db_url=db_url).returncode == 0
    engine = sqlalchemy.create_engine(db_url)

    monkeypatch.setattr(settings, "database_url", db_url)
    monkeypatch.setattr(db_module, "engine", engine)

    def boom():
        raise RuntimeError("migration exploded")

    logged: list[str] = []
    monkeypatch.setattr(db_module, "run_migrations", boom)
    monkeypatch.setattr(db_module.log, "exception", lambda msg, *a, **k: logged.append(str(msg)))

    db_module.init_db()  # must not raise

    assert any("migration failed" in message.lower() for message in logged)
    # The database is still usable even though the upgrade failed.
    assert MODEL_TABLES <= set(inspect(engine).get_table_names())


def test_the_docker_image_ships_what_the_app_needs_at_runtime():
    """Migrations and evaluation suites must be in the image.

    init_db() upgrades the schema on boot, which needs migrations/ and
    alembic.ini; the evaluation harness needs evals/. All three live outside
    app/, so a Dockerfile that only copies app/ produces an image that breaks
    on first boot. This caught exactly that.
    """
    root = BACKEND.parent
    dockerfile = (BACKEND / "Dockerfile").read_text()

    for required in ("backend/migrations", "backend/alembic.ini", "evals"):
        assert f"COPY {required}" in dockerfile, f"the image does not copy {required}"

    # The build context must be the project root for those paths to resolve.
    compose = (root / "docker-compose.yml").read_text()
    assert "dockerfile: backend/Dockerfile" in compose
    assert "context: ." in compose


# =====================================================================
# Upgrading a database that already has data in it
#
# Every existing install takes this path. A migration that drops rows, or
# leaves the app unable to read what survived, is the one bug in this file
# that destroys something the user cannot get back.
# =====================================================================

import sqlite3  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime  # noqa: E402


def _seed_baseline(path: str) -> dict[str, int]:
    """Insert representative rows into a database at the baseline revision."""
    now = datetime.utcnow().isoformat(" ")
    conn = sqlite3.connect(path)

    conversation = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO conversations (id,title,pinned,archived,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (conversation, "Deploy planning", 1, 0, now, now),
    )
    for role, text in [("user", "how do I deploy?"), ("assistant", "Use the runbook.")]:
        conn.execute(
            "INSERT INTO messages (conversation_id,role,content,tokens,latency_ms,meta,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (conversation, role, text, 0, 0, "{}", now),
        )
    conn.execute(
        "INSERT INTO memories (id,kind,content,source,confidence,pinned,meta,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), "fact", "The deploy key lives in the vault.", "manual", 0.8, 1, "{}", now, now),
    )
    document = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO documents (id,name,path,hash,size_bytes,chunk_count,meta,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (document, "runbook.md", "/kb/runbook.md", "h1", 120, 1, "{}", now),
    )
    conn.execute(
        "INSERT INTO chunks (id,document_id,chunk_index,content,meta,created_at) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), document, 0, "Roll back with the previous image tag.", "{}", now),
    )
    conn.commit()

    tables = ["conversations", "messages", "memories", "documents", "chunks"]
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    conn.close()
    return counts


def test_upgrading_a_populated_database_keeps_every_row(tmp_path, db_url):
    """The path every existing install takes on update."""
    assert alembic("upgrade", BASELINE, db_url=db_url).returncode == 0
    path = db_url.replace("sqlite:///", "")

    before = _seed_baseline(path)
    assert alembic("upgrade", "head", db_url=db_url).returncode == 0

    conn = sqlite3.connect(path)
    after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
    conn.close()

    assert after == before, f"rows lost during upgrade: {before} -> {after}"


def test_upgrading_preserves_the_content_not_just_the_row_count(tmp_path, db_url):
    """A migration that rewrites a table could keep the count and lose the
    values, which a COUNT(*) check would miss entirely."""
    assert alembic("upgrade", BASELINE, db_url=db_url).returncode == 0
    path = db_url.replace("sqlite:///", "")
    _seed_baseline(path)

    assert alembic("upgrade", "head", db_url=db_url).returncode == 0

    conn = sqlite3.connect(path)
    assert conn.execute("SELECT title FROM conversations").fetchone()[0] == "Deploy planning"
    assert conn.execute("SELECT pinned FROM conversations").fetchone()[0] == 1
    assert "previous image tag" in conn.execute("SELECT content FROM chunks").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE role='assistant'").fetchone()[0] == 1
    conn.close()


def test_columns_added_later_are_usable_on_pre_existing_rows(tmp_path, db_url):
    """An added column defaults to NULL on old rows; the app has to cope with
    that rather than only working for data created after the upgrade."""
    assert alembic("upgrade", BASELINE, db_url=db_url).returncode == 0
    path = db_url.replace("sqlite:///", "")
    _seed_baseline(path)
    assert alembic("upgrade", "head", db_url=db_url).returncode == 0

    conn = sqlite3.connect(path)
    columns = [c[1] for c in conn.execute("PRAGMA table_info(conversations)")]
    assert "persona" in columns and "system_prompt" in columns

    # The old row can be updated through the new column.
    conn.execute("UPDATE conversations SET persona='engineer'")
    conn.commit()
    assert conn.execute("SELECT persona FROM conversations").fetchone()[0] == "engineer"
    conn.close()


def test_the_app_serves_a_database_that_was_upgraded_from_baseline(tmp_path):
    """The end-to-end version: migrate a populated old database, then boot the
    real app against it in a fresh interpreter and read the pre-existing data
    back through the API. Run out-of-process because the app binds its engine
    at import time, and monkeypatching that in-process proves nothing about
    what happens on a real boot.
    """
    path = tmp_path / "upgraded.db"
    url = f"sqlite:///{path}"

    assert alembic("upgrade", BASELINE, db_url=url).returncode == 0
    _seed_baseline(str(path))
    assert alembic("upgrade", "head", db_url=url).returncode == 0

    probe = """
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as c:
    assert c.get("/health").json()["schema"]["up_to_date"] is True

    conversations = c.get("/v1/conversations").json()["conversations"]
    assert len(conversations) == 1
    assert conversations[0]["title"] == "Deploy planning"
    assert conversations[0]["message_count"] == 2

    # Data written before the column existed is readable and writable.
    cid = conversations[0]["id"]
    assert c.patch(f"/v1/conversations/{cid}", json={"persona": "engineer"}).status_code == 200

    messages = c.get(f"/v1/conversations/{cid}").json()["messages"]
    assert [m["content"] for m in messages] == ["how do I deploy?", "Use the runbook."]

    # Tables added by later migrations are live.
    assert c.get("/v1/mcp/servers").status_code == 200
    # And the upgraded database still accepts new writes.
    assert c.post("/v1/chat", json={"message": "hello"}).status_code == 200

print("OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=BACKEND,
        env={
            "PATH": "/usr/bin:/bin",
            "DATABASE_URL": url,
            "KNOWLEDGE_DIR": str(tmp_path / "kb"),
            "PYTHONPATH": str(BACKEND),
            "HOME": "/tmp",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert "OK" in result.stdout, result.stderr[-1500:]
