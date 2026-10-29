"""Integration tests for the timestamp-driven EventTracker."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.mock_ai_model import MockAIModel
from app.adapters.mock_camera_event_detector import MockCameraEventDetector
from app.db.repositories import (
    AlertRepository,
    CameraEventRepository,
    ConcreteSituationRepository,
    EvaluationRepository,
    HandledCameraEventRepository,
    MatchRepository,
    SituationRepository,
)
from app.db.tables import (
    Alert,
    CameraEvent,
    ConcreteSituation,
    Evaluation,
    HandledCameraEvent,
    Match,
    Situation,
)
from app.domain.models import Answer, ConcreteSituationStatus, EvaluatorResult
from app.domain.time import normalize_to_utc
from app.ports.ai_model import AIModel, EvidenceRequest
from app.services.evaluator import Evaluator
from app.services.event_tracker import EventTracker
from app.services.situation_service import SituationService


class FixedAIModel:
    def __init__(self, result: EvaluatorResult | Exception) -> None:
        self.result = result
        self.calls: list[EvidenceRequest] = []

    def check_event(self, request: EvidenceRequest) -> EvaluatorResult:
        self.calls.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def create_situation(self, text: str) -> object:
        raise NotImplementedError


class SequenceAIModel:
    def __init__(self, results: list[EvaluatorResult]) -> None:
        self.results = iter(results)
        self.calls: list[EvidenceRequest] = []

    def check_event(self, request: EvidenceRequest) -> EvaluatorResult:
        self.calls.append(request)
        return next(self.results)

    def create_situation(self, text: str) -> object:
        raise NotImplementedError


def _seed_timestamp_events(
    session: Session,
    fixture_path: Path,
    entries: list[tuple[int, str]],
) -> None:
    fixture_path.write_text(
        yaml.safe_dump(
            {
                "camera_events": [
                    {
                        "id": event_id,
                        "camera_id": 1,
                        "timestamp": timestamp,
                        "frame_ref": f"frame-{event_id}.jpg",
                        "video_ref": f"video-{event_id}.mp4",
                    }
                    for event_id, timestamp in entries
                ]
            }
        ),
        encoding="utf-8",
    )
    assert MockCameraEventDetector(session, fixture_path).seed() == len(entries)
    session.flush()
    repository = CameraEventRepository(session)
    for event_id, timestamp in entries:
        camera_event = repository.get(event_id)
        assert camera_event is not None
        assert camera_event.timestamp == normalize_to_utc(
            datetime.fromisoformat(timestamp)
        )


def _tracker(
    session: Session, ai_model: AIModel
) -> EventTracker:
    return EventTracker(
        camera_event_repository=CameraEventRepository(session),
        handled_repository=HandledCameraEventRepository(session),
        situation_repository=SituationRepository(session),
        concrete_situation_repository=ConcreteSituationRepository(session),
        match_repository=MatchRepository(session),
        alert_repository=AlertRepository(session),
        evaluation_repository=EvaluationRepository(session),
        evaluator=Evaluator(ai_model),
        session=session,
    )


def _create_situation(
    session: Session, ai_model: MockAIModel, text: str, camera_id: int
) -> None:
    SituationService(
        ai_model, SituationRepository(session), session
    ).create(text, camera_id)


def test_demo_scenarios_a_through_f(db_session: Session) -> None:
    detector_model = MockAIModel()
    detector = MockCameraEventDetector(db_session)
    assert detector.seed() == 16
    for text, camera_id in [
        ("Alert me if you see smoke", 1),
        ("Alert me if someone leaves a package at the door and then walks away", 2),
        ("Alert me if you see smoke", 3),
        (
            "Alert me if someone leaves a package at the door and then walks away",
            4,
        ),
        (
            "Alert me if someone leaves a package at the door and then walks away",
            5,
        ),
        ("Alert me if someone loiters in front of the embassy", 6),
    ]:
        _create_situation(db_session, detector_model, text, camera_id)

    model = MockAIModel()
    tracker = _tracker(db_session, model)
    assert tracker.process_unhandled() == 16
    db_session.commit()

    alerts = db_session.scalars(select(Alert).order_by(Alert.created_at)).all()
    assert [alert.situation_id for alert in alerts] == [1, 2, 6]
    assert [alert.concrete_situation_id for alert in alerts] == [1, 2, 4]
    assert alerts[0].explanation == (
        'Event 1 "Smoke is visible" matched camera event 101 (confidence 0.93)'
    )
    assert "camera event 201 (confidence 0.88)" in alerts[1].explanation
    assert "camera event 203 (confidence 0.86)" in alerts[1].explanation

    concrete_situations = db_session.scalars(
        select(ConcreteSituation).order_by(ConcreteSituation.id)
    ).all()
    assert [row.status for row in concrete_situations] == [
        ConcreteSituationStatus.COMPLETED,
        ConcreteSituationStatus.COMPLETED,
        ConcreteSituationStatus.EXPIRED,
        ConcreteSituationStatus.COMPLETED,
    ]
    assert [
        (match.concrete_situation_id, match.position, match.camera_event_id)
        for match in db_session.scalars(
            select(Match).order_by(Match.concrete_situation_id, Match.position)
        )
    ] == [
        (1, 0, 101),
        (2, 0, 201),
        (2, 1, 202),
        (2, 2, 203),
        (3, 0, 501),
        (4, 0, 601),
        (4, 1, 602),
        (4, 2, 603),
    ]
    request_ids = [
        call.camera_event_id
        for call in model.calls
        if isinstance(call, EvidenceRequest)
    ]
    assert set(request_ids) == {
        101,
        201,
        202,
        203,
        204,
        301,
        401,
        501,
        502,
        601,
        602,
        603,
    }
    assert len(request_ids) == 12
    assert model.errors == []
    evaluations = db_session.scalars(select(Evaluation)).all()
    assert len(evaluations) == 12
    assert (
        next(row for row in evaluations if row.camera_event_id == 301).answer
        is Answer.UNSURE
    )
    assert db_session.get(HandledCameraEvent, 606) is not None
    repeated = db_session.get(CameraEvent, 101)
    assert repeated is not None
    assert tracker.process(repeated) == []


def test_tracker_marks_camera_events_handled_without_situations(
    db_session: Session,
) -> None:
    MockCameraEventDetector(db_session).seed()
    model = MockAIModel()
    tracker = _tracker(db_session, model)

    assert tracker.process_unhandled() == 16
    db_session.commit()

    assert len(db_session.scalars(select(HandledCameraEvent)).all()) == 16
    assert model.calls == []


def test_tracker_does_not_commit_unrelated_caller_changes(
    db_session: Session,
) -> None:
    fixture_model = MockAIModel()
    MockCameraEventDetector(db_session).seed()
    situation = SituationService(
        fixture_model, SituationRepository(db_session), db_session
    ).create("Alert me if you see smoke", 1)
    camera_event = CameraEventRepository(db_session).get(101)
    assert camera_event is not None

    situation.description = "Caller-owned uncommitted edit"
    tracker = _tracker(db_session, MockAIModel())
    tracker.process(camera_event)
    db_session.rollback()
    db_session.expire(situation)

    assert situation.description == "Alert me if you see smoke"


def test_process_unhandled_refetches_earliest_event_after_each_process(
    db_session: Session,
) -> None:
    first_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            CameraEvent(
                id=9401,
                camera_id=1,
                timestamp=first_timestamp,
                frame_ref="frame-9401.jpg",
                video_ref="video-9401.mp4",
            ),
            CameraEvent(
                id=9403,
                camera_id=1,
                timestamp=first_timestamp.replace(second=20),
                frame_ref="frame-9403.jpg",
                video_ref="video-9403.mp4",
            ),
        ]
    )
    db_session.commit()
    fixture_model = MockAIModel()
    _create_situation(db_session, fixture_model, "Alert me if you see smoke", 1)

    class InsertingAIModel:
        def __init__(self) -> None:
            self.calls: list[int] = []
            self.inserted = False

        def check_event(self, request: EvidenceRequest) -> EvaluatorResult:
            self.calls.append(request.camera_event_id)
            if not self.inserted:
                self.inserted = True
                db_session.add(
                    CameraEvent(
                        id=9402,
                        camera_id=1,
                        timestamp=first_timestamp.replace(second=10),
                        frame_ref="frame-9402.jpg",
                        video_ref="video-9402.mp4",
                    )
                )
            return EvaluatorResult(answer=Answer.NO, confidence=0.9)

        def create_situation(self, text: str) -> object:
            raise NotImplementedError

    model = InsertingAIModel()

    assert _tracker(db_session, model).process_unhandled() == 3

    assert model.calls == [9401, 9402, 9403]


@pytest.mark.parametrize(("confidence", "expected_concrete_count"), [(0.79, 0), (0.8, 1)])
def test_tracker_advances_only_at_confidence_threshold(
    db_session: Session, confidence: float, expected_concrete_count: int
) -> None:
    fixture_model = MockAIModel()
    MockCameraEventDetector(db_session).seed()
    _create_situation(db_session, fixture_model, "Alert me if you see smoke", 1)
    db_session.commit()
    tracker = _tracker(
        db_session,
        FixedAIModel(EvaluatorResult(answer=Answer.YES, confidence=confidence)),
    )

    camera_event = db_session.get(CameraEvent, 101)
    assert camera_event is not None
    tracker.process(camera_event)
    db_session.commit()

    assert len(db_session.scalars(select(ConcreteSituation)).all()) == expected_concrete_count
    assert len(db_session.scalars(select(Evaluation)).all()) == 1


def test_tracker_model_failure_logs_unsure_without_advancing(db_session: Session) -> None:
    fixture_model = MockAIModel()
    MockCameraEventDetector(db_session).seed()
    _create_situation(
        db_session,
        fixture_model,
        "Alert me if someone leaves a package at the door and then walks away",
        1,
    )
    db_session.add(
        CameraEvent(
            id=901,
            camera_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            frame_ref="frame-901.jpg",
            video_ref="video-901.mp4",
        )
    )
    db_session.commit()
    tracker = _tracker(db_session, MockAIModel())

    camera_event = db_session.get(CameraEvent, 901)
    assert camera_event is not None
    tracker.process(camera_event)
    db_session.commit()

    evaluation = db_session.scalar(
        select(Evaluation).where(Evaluation.camera_event_id == 901)
    )
    assert evaluation is not None
    assert evaluation.answer is Answer.UNSURE
    assert evaluation.confidence == 0
    assert db_session.scalars(select(ConcreteSituation)).all() == []


def test_tracker_expiry_normalizes_offset_timestamps(
    db_session: Session, tmp_path: Path
) -> None:
    fixture_model = MockAIModel()
    _seed_timestamp_events(
        db_session,
        tmp_path / "events.yaml",
        [
            (9201, "2025-01-01T12:00:00+01:00"),
            (9202, "2025-01-01T11:05:01+00:00"),
        ],
    )
    _create_situation(
        db_session,
        fixture_model,
        "Alert me if someone leaves a package at the door and then walks away",
        1,
    )
    db_session.commit()

    class Answers:
        def check_event(self, request: EvidenceRequest) -> EvaluatorResult:
            result = (
                EvaluatorResult(answer=Answer.YES, confidence=0.9)
                if request.camera_event_id == 9201
                else EvaluatorResult(answer=Answer.NO, confidence=0.9)
            )
            return result

        def create_situation(self, text: str) -> object:
            raise NotImplementedError

    tracker = _tracker(db_session, Answers())
    tracker.process_unhandled()
    db_session.commit()

    concrete = db_session.scalars(select(ConcreteSituation)).one()
    assert concrete.status is ConcreteSituationStatus.EXPIRED
    assert normalize_to_utc(concrete.last_match_at) == datetime(
        2025, 1, 1, 11, 0, tzinfo=timezone.utc
    )


def test_tracker_cooldown_normalizes_offset_timestamps(
    db_session: Session, tmp_path: Path
) -> None:
    fixture_model = MockAIModel()
    _seed_timestamp_events(
        db_session,
        tmp_path / "events.yaml",
        [
            (9301, "2025-01-01T12:00:00+01:00"),
            (9302, "2025-01-01T11:04:59+00:00"),
            (9303, "2025-01-01T11:05:01+00:00"),
        ],
    )
    _create_situation(db_session, fixture_model, "Alert me if you see smoke", 1)
    db_session.commit()
    model = SequenceAIModel(
        [
            EvaluatorResult(answer=Answer.YES, confidence=0.9),
            EvaluatorResult(answer=Answer.YES, confidence=0.9),
        ]
    )

    assert _tracker(db_session, model).process_unhandled() == 3

    assert [request.camera_event_id for request in model.calls] == [9301, 9303]
    completed = db_session.scalars(
        select(ConcreteSituation).order_by(ConcreteSituation.id)
    ).all()
    assert [item.status for item in completed] == [
        ConcreteSituationStatus.COMPLETED,
        ConcreteSituationStatus.COMPLETED,
    ]
