from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

log = logging.getLogger(__name__)

# The first migration. Databases created before Alembic was introduced match
# this schema, so they can be stamped here and then upgraded forward.
BASELINE_REVISION = "3fce4a4a6ed7"

connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args,
)

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        # WAL lets readers run while a write is in flight.
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        # SQLite still serialises writers. The default 5s meant a write could
        # fail outright while a long agent run held its transaction -- losing
        # a user's message to a transient lock. 30s is long enough to outlast
        # any commit here and still surface a genuine deadlock rather than
        # hanging forever.
        cur.execute("PRAGMA busy_timeout=30000")
        # Durable enough for a local assistant, and markedly faster than the
        # default FULL sync on every commit.
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Bring the schema up to date. Safe to call on every boot.

    Three cases, in order:

    * **Brand new database** -- create every table directly, then stamp it at
      head so it is a valid baseline for future migrations.
    * **Existing database behind head** -- run the pending migrations. Without
      this, adding a column to a model would leave running deployments with a
      schema the code cannot use.
    * **Existing database at head** -- create_all covers any brand new tables
      and nothing else happens.

    Migration failures are logged loudly but do not stop boot: a running ORION
    that reports a schema problem at /health is more useful than one that
    refuses to start.
    """
    try:
        existing = inspect(engine).get_table_names()
    except Exception:  # pragma: no cover - inspection failure is fatal anyway
        existing = []

    fresh = "conversations" not in existing
    if fresh:
        Base.metadata.create_all(bind=engine)
        try:
            stamp_head()
        except Exception:
            log.debug("Could not stamp Alembic revision", exc_info=True)
        return

    # Existing database: let Alembic bring it forward.
    try:
        if current_revision() is None:
            # Pre-Alembic database: assume it matches the baseline, then upgrade.
            from alembic import command

            command.stamp(alembic_config(), BASELINE_REVISION)
        run_migrations()
    except Exception:
        log.exception(
            "Database migration failed. The schema may be out of date; "
            "check /health and run ./scripts/migrate.sh"
        )
    # Catches any table added to the models without a migration.
    Base.metadata.create_all(bind=engine)


def alembic_config():
    """Alembic config pointed at this package's migrations directory."""
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def current_revision() -> str | None:
    """The migration revision this database is currently at, if any."""
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def head_revision() -> str | None:
    """The newest revision available on disk."""
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def stamp_head() -> None:
    """Mark the database as being at the latest revision without running DDL."""
    from alembic import command

    if current_revision() is None:
        command.stamp(alembic_config(), "head")


def run_migrations() -> None:
    """Apply any pending migrations."""
    from alembic import command

    command.upgrade(alembic_config(), "head")


def migration_status() -> dict[str, object]:
    """Whether the database schema matches the code's expectations."""
    try:
        current, head = current_revision(), head_revision()
        return {
            "current_revision": current,
            "head_revision": head,
            "up_to_date": current == head,
            "error": None,
        }
    except Exception as exc:
        return {"current_revision": None, "head_revision": None, "up_to_date": None,
                "error": str(exc)[:200]}


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
