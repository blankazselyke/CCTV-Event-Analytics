"""Tests for the database-enforced uniqueness constraints."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.tables import (
    Alert,
    CameraEvent,
    ConcreteSituation,
    Evaluation,
    Match,
    Situation,
)
from app.domain.models import Answer, ConcreteSituationStatus


def _base_rows(session: Session) -> None:
    session.add_all(
        [
            CameraEvent(
                id=1,
                camera_id=1,
                timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                frame_ref="frame.jpg",
                video_ref="video.mp4",
            ),
            Situation(
                id=1,
                description="Smoke is visible",
                camera_id=1,
                wait_time_seconds=300,
                cooldown_seconds=300,
            ),
        ]
    )
    session.flush()


def _concrete(
    concrete_id: int,
    status: ConcreteSituationStatus = ConcreteSituationStatus.OPEN,
) -> ConcreteSituation:
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return ConcreteSituation(
        id=concrete_id,
        situation_id=1,
        status=status,
        started_at=timestamp,
        last_match_at=timestamp,
        completed_at=timestamp if status is ConcreteSituationStatus.COMPLETED else None,
    )


def test_database_allows_at_most_one_open_concrete_situation(
    db_session: Session,
) -> None:
    _base_rows(db_session)
    db_session.add(_concrete(1))
    db_session.flush()
    db_session.add(_concrete(2))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_allows_same_camera_event_only_once_per_concrete_situation(
    db_session: Session,
) -> None:
    _base_rows(db_session)
    db_session.add(_concrete(1))
    db_session.flush()
    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    db_session.add(
        Match(
            concrete_situation_id=1,
            position=0,
            camera_event_id=1,
            confidence=0.9,
            matched_at=when,
        )
    )
    db_session.flush()
    db_session.add(
        Match(
            concrete_situation_id=1,
            position=1,
            camera_event_id=1,
            confidence=0.9,
            matched_at=when,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_allows_at_most_one_alert_per_concrete_situation(
    db_session: Session,
) -> None:
    _base_rows(db_session)
    db_session.add(_concrete(1, ConcreteSituationStatus.COMPLETED))
    db_session.flush()
    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    first = Alert(
        situation_id=1,
        description="Smoke is visible",
        concrete_situation_id=1,
        created_at=when,
        explanation="Smoke was visible.",
    )
    second = Alert(
        situation_id=1,
        description="Smoke is visible",
        concrete_situation_id=1,
        created_at=when,
        explanation="Smoke was visible.",
    )
    db_session.add(first)
    db_session.flush()
    db_session.add(second)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_allows_at_most_one_evaluation_per_camera_event_and_situation(
    db_session: Session,
) -> None:
    _base_rows(db_session)
    first = Evaluation(
        camera_event_id=1,
        situation_id=1,
        position=0,
        answer=Answer.YES,
        confidence=0.9,
    )
    second = Evaluation(
        camera_event_id=1,
        situation_id=1,
        position=1,
        answer=Answer.NO,
        confidence=0.9,
    )
    db_session.add(first)
    db_session.flush()
    db_session.add(second)

    with pytest.raises(IntegrityError):
        db_session.flush()
