from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    eng = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
    if is_sqlite:
        @event.listens_for(eng, "connect")
        def _on_connect(dbapi_conn, _):
            # Let SQLAlchemy control transactions so SAVEPOINTs (per-row CSV import) work correctly.
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        @event.listens_for(eng, "begin")
        def _on_begin(conn):
            conn.exec_driver_sql("BEGIN")
    return eng


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
