"""Tests for repository behavior used by subsequent processing phases."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.repositories import (
    CameraEventRepository,
    HandledCameraEventRepository,
    SituationRepository,
)
from app.db.tables import CameraEvent, Situation, SituationEvent


def test_unhandled_camera_events_are_ordered_by_timestamp_then_id(
    db_session: Session,
) -> None:
    repository = CameraEventRepository(db_session)
    db_session.add_all(
        [
            CameraEvent(
                id=2,
                camera_id=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 10, tzinfo=timezone.utc),
                frame_ref="2.jpg",
                video_ref="2.mp4",
            ),
            CameraEvent(
                id=3,
                camera_id=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                frame_ref="3.jpg",
                video_ref="3.mp4",
            ),
            CameraEvent(
                id=1,
                camera_id=1,
                timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                frame_ref="1.jpg",
                video_ref="1.mp4",
            ),
        ]
    )
    db_session.flush()
    db_session.expire_all()

    ordered_events = repository.list_unhandled_ordered()
    assert [event.id for event in ordered_events] == [1, 3, 2]
    assert all(event.timestamp.tzinfo is timezone.utc for event in ordered_events)

    HandledCameraEventRepository(db_session).mark_handled(
        3, datetime(2025, 1, 1, 12, 1, tzinfo=timezone.utc)
    )
    db_session.flush()

    assert [event.id for event in repository.list_unhandled_ordered()] == [1, 2]


def test_situation_repository_lists_by_camera_and_orders_events(
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            Situation(
                id=1,
                description="Rule",
                camera_id=7,
                wait_time_seconds=300,
                cooldown_seconds=0,
            ),
            SituationEvent(
                situation_id=1,
                position=1,
                description="second",
                evidence="frame",
            ),
            SituationEvent(
                situation_id=1,
                position=0,
                description="first",
                evidence="video",
            ),
        ]
    )
    db_session.flush()
    repository = SituationRepository(db_session)

    assert [s.id for s in repository.list_for_camera(7)] == [1]
    assert [e.position for e in repository.list_events(1)] == [0, 1]
