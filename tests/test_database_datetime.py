"""Tests for timezone-aware UTC datetime values loaded from SQLite."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.tables import (
    Alert,
    CameraEvent,
    ConcreteSituation,
    Evaluation,
    HandledCameraEvent,
    Match,
    Situation,
    SituationEvent,
)
from app.domain.models import Answer, ConcreteSituationStatus, EvidenceType


def test_datetimes_from_every_table_are_aware_utc(db_session: Session) -> None:
    offset = timezone(timedelta(hours=1))
    timestamp = datetime(2025, 1, 1, 12, 0, tzinfo=offset)
    expected = datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc)

    db_session.add(
        CameraEvent(
            id=1,
            camera_id=1,
            timestamp=timestamp,
            frame_ref="frame.jpg",
            video_ref="video.mp4",
        )
    )
    db_session.add(
        Situation(
            id=1,
            description="A person is visible",
            camera_id=1,
            wait_time_seconds=300,
            cooldown_seconds=0,
        )
    )
    db_session.flush()
    db_session.add_all(
        [
            HandledCameraEvent(camera_event_id=1, handled_at=timestamp),
            SituationEvent(
                situation_id=1,
                position=0,
                description="A person is visible",
                evidence=EvidenceType.FRAME,
            ),
            ConcreteSituation(
                id=1,
                situation_id=1,
                status=ConcreteSituationStatus.COMPLETED,
                started_at=timestamp,
                last_match_at=timestamp,
                completed_at=timestamp,
            ),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            Match(
                concrete_situation_id=1,
                position=0,
                camera_event_id=1,
                confidence=0.9,
                matched_at=timestamp,
            ),
            Alert(
                situation_id=1,
                description="A person is visible",
                concrete_situation_id=1,
                created_at=timestamp,
                explanation="Matched.",
            ),
            Evaluation(
                camera_event_id=1,
                situation_id=1,
                position=0,
                answer=Answer.YES,
                confidence=0.9,
            ),
        ]
    )
    db_session.commit()
    db_session.expire_all()

    loaded_datetimes = [
        db_session.get(CameraEvent, 1).timestamp,
        db_session.get(HandledCameraEvent, 1).handled_at,
        db_session.get(ConcreteSituation, 1).started_at,
        db_session.get(ConcreteSituation, 1).last_match_at,
        db_session.get(ConcreteSituation, 1).completed_at,
        db_session.get(Match, (1, 0)).matched_at,
        db_session.get(Alert, 1).created_at,
    ]

    assert all(value is not None for value in loaded_datetimes)
    assert all(value.utcoffset() == timedelta(0) for value in loaded_datetimes)
    assert all(value == expected for value in loaded_datetimes)
