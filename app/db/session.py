"""SQLAlchemy engine, schema, and session helpers."""

from collections.abc import Callable
import sqlite3

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db.tables import Base


def create_database_engine(database_url: str = "sqlite+pysqlite:///:memory:") -> Engine:
    """Create an engine and enable SQLite foreign-key enforcement."""
    engine = create_engine(database_url)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(
            dbapi_connection: sqlite3.Connection, connection_record: object
        ) -> None:
            _ = connection_record
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    """Create all mapped tables and indexes."""
    Base.metadata.create_all(engine)


def create_session_factory(engine: Engine) -> Callable[[], Session]:
    """Create a session factory for the supplied engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
