"""Shared test fixtures."""

import pytest
from sqlalchemy.orm import Session

from app.db.session import create_database_engine, create_schema


@pytest.fixture
def db_session() -> Session:
    engine = create_database_engine()
    create_schema(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
