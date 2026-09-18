import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("KNOWLEDGE_DIR", tempfile.mkdtemp())
os.environ.setdefault("OFFLINE_FALLBACK_ENABLED", "true")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")
# Skill distillation makes an extra model call per run; tests that exercise it
# enable it explicitly so other tests can assert exact call counts.
os.environ.setdefault("SKILL_LEARNING_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal, init_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
