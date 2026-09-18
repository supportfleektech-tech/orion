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
