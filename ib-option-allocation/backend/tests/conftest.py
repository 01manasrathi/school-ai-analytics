import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PBKDF2_ITERATIONS", "1000")  # fast password hashing in tests

from app import models  # noqa: E402,F401
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_data  # noqa: E402


def _memory_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _c(dbapi_conn, _):
        dbapi_conn.isolation_level = None

    @event.listens_for(engine, "begin")
    def _b(conn):
        conn.exec_driver_sql("BEGIN")

    return engine


@pytest.fixture(scope="session")
def seeded_template():
    """Seed once per test session; each test gets its own copy via the SQLite backup API."""
    engine = _memory_engine()
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        seed_data(s)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(seeded_template):
    engine = _memory_engine()
    src, dst = seeded_template.raw_connection(), engine.raw_connection()
    try:
        src.driver_connection.backup(dst.driver_connection)
    finally:
        src.close()
        dst.close()
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(db_session):
    def _get_db():
        db = db_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _token(client, user, pw):
    return {"Authorization": "Bearer " + client.post("/api/auth/login", json={"username": user, "password": pw}).json()["token"]}


@pytest.fixture()
def admin(client):
    return _token(client, "admin", "admin123")


@pytest.fixture()
def viewer(client):
    return _token(client, "viewer", "viewer123")
