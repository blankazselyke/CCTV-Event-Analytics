"""Tests for Situation creation and single-pair evaluation."""

from datetime import datetime
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.mock_ai_model import MockAIModel
from app.db.repositories import SituationRepository
from app.db.tables import CameraEvent, Situation, SituationEvent
from app.domain.models import Answer, EvaluatorResult, EvidenceType
from app.domain.validation import InvalidSituationError
from app.ports.ai_model import EvidenceRequest
from app.services.evaluator import Evaluator
from app.services.situation_service import SituationService


class ReturningAIModel:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requests: list[EvidenceRequest] = []

    def check_event(self, request: EvidenceRequest) -> EvaluatorResult:
        self.requests.append(request)
        return cast(EvaluatorResult, self.result)

    def create_situation(self, text: str) -> object:
        raise NotImplementedError


def test_situation_service_saves_valid_model_output(db_session: Session) -> None:
    model = MockAIModel()
    service = SituationService(model, SituationRepository(db_session), db_session)

    situation = service.create("Alert me if you see smoke", camera_id=1)

    assert situation.id is not None
    assert situation.wait_time_seconds == 300
    assert situation.cooldown_seconds == 300
    events = db_session.scalars(
        select(SituationEvent).where(SituationEvent.situation_id == situation.id)
    ).all()
    assert [(event.position, event.description, event.evidence) for event in events] == [
        (0, "Smoke is visible", EvidenceType.FRAME)
    ]
    assert model.calls == ["Alert me if you see smoke"]
    assert model.errors == []


def test_situation_service_does_not_save_invalid_output(db_session: Session) -> None:
    model = MockAIModel()
    service = SituationService(model, SituationRepository(db_session), db_session)

    with pytest.raises(InvalidSituationError):
        service.create(
            "Alert me if the model returns invalid situation data", camera_id=1
        )

    assert db_session.scalars(select(Situation)).all() == []
    assert db_session.scalars(select(SituationEvent)).all() == []


@pytest.mark.parametrize(
    ("evidence", "expected_ref"),
    [(EvidenceType.FRAME, "frame.jpg"), (EvidenceType.VIDEO, "video.mp4")],
)
def test_evaluator_sends_the_requested_evidence(
    evidence: EvidenceType, expected_ref: str
) -> None:
    model = ReturningAIModel(EvaluatorResult(answer=Answer.YES, confidence=0.9))
    evaluator = Evaluator(model)
    camera_event = CameraEvent(
        id=11,
        camera_id=1,
        timestamp=datetime(2025, 1, 1),
        frame_ref="frame.jpg",
        video_ref="video.mp4",
    )
    situation_event = SituationEvent(
        situation_id=1,
        position=0,
        description="A person is visible",
        evidence=evidence,
    )

    result = evaluator.check(camera_event, situation_event)

    assert result.answer is Answer.YES
    assert model.requests == [
        EvidenceRequest(11, evidence, expected_ref, "A person is visible")
    ]


def test_evaluator_converts_model_failure_to_unsure(caplog: pytest.LogCaptureFixture) -> None:
    model = ReturningAIModel(RuntimeError("model offline"))
    evaluator = Evaluator(model)
    camera_event = CameraEvent(
        id=11,
        camera_id=1,
        timestamp=datetime(2025, 1, 1),
        frame_ref="frame.jpg",
        video_ref="video.mp4",
    )
    situation_event = SituationEvent(
        situation_id=1,
        position=0,
        description="A person is visible",
        evidence=EvidenceType.FRAME,
    )

    result = evaluator.check(camera_event, situation_event)

    assert result.answer is Answer.UNSURE
    assert result.confidence == 0
    assert "model offline" in caplog.text


def test_evaluator_converts_invalid_model_result_to_unsure() -> None:
    model = ReturningAIModel({"answer": "maybe", "confidence": 2})
    evaluator = Evaluator(model)
    camera_event = CameraEvent(
        id=11,
        camera_id=1,
        timestamp=datetime(2025, 1, 1),
        frame_ref="frame.jpg",
        video_ref="video.mp4",
    )
    situation_event = SituationEvent(
        situation_id=1,
        position=0,
        description="A person is visible",
        evidence=EvidenceType.FRAME,
    )

    result = evaluator.check(camera_event, situation_event)

    assert result.answer is Answer.UNSURE
    assert result.confidence == 0
