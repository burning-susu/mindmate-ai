from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import sessionmaker


def create_sqlite_engine(path: Path) -> Engine:
    engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker:
    """Create the application-scoped SQLAlchemy session factory."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def quick_check(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text("PRAGMA quick_check")).scalar_one())
