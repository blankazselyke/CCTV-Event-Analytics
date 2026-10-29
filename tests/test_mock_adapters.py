"""Tests for the fixture-backed model and camera event detector."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.adapters.mock_ai_model import (
    FixtureError,
    MissingFixtureError,
    MockAIModel,
)
from app.adapters.mock_camera_event_detector import MockCameraEventDetector
from app.db.tables import CameraEvent
from app.domain.models import Answer, EvidenceType
from app.domain.validation import InvalidSituationError, validate_situation
from app.ports.ai_model import EvidenceRequest


def test_mock_ai_model_returns_fixture_result_and_records_call() -> None:
    model = MockAIModel()
    request = EvidenceRequest(
        camera_event_id=101,
        evidence_type=EvidenceType.FRAME,
        evidence_ref="frame-101.jpg",
        question="Smoke is visible",
    )

    result = model.check_event(request)

    assert result.answer is Answer.YES
    assert result.confidence == 0.93
    assert model.calls == [request]
    assert model.errors == []


def test_mock_ai_model_returns_raw_situation_fixture() -> None:
    model = MockAIModel()
    text = "Alert me if the model returns invalid situation data"

    raw_situation = model.create_situation(text)
    assert model.calls == [text]
    with pytest.raises(InvalidSituationError):
        validate_situation(raw_situation)
    assert model.errors == []


def test_mock_ai_model_fixture_error_is_recorded_and_raised() -> None:
    model = MockAIModel()
    request = EvidenceRequest(
        camera_event_id=901,
        evidence_type=EvidenceType.FRAME,
        evidence_ref="frame-901.jpg",
        question="Smoke is visible",
    )

    with pytest.raises(TimeoutError, match="timeout"):
        model.check_event(request)

    assert model.calls == [request]
    assert len(model.errors) == 1
    assert isinstance(model.errors[0], TimeoutError)


def test_mock_ai_model_raises_for_missing_fixture() -> None:
    model = MockAIModel()
    request = EvidenceRequest(
        camera_event_id=999,
        evidence_type=EvidenceType.FRAME,
        evidence_ref="frame-999.jpg",
        question="Missing question",
    )

    with pytest.raises(MissingFixtureError):
        model.check_event(request)

    assert model.calls == [request]
    assert isinstance(model.errors[0], MissingFixtureError)


def test_mock_ai_model_rejects_malformed_answer_fixture(tmp_path: Path) -> None:
    fixture_path = tmp_path / "answers.yaml"
    fixture_path.write_text(
        "answers:\n  '1':\n    question: {answer: maybe, confidence: 2}\n",
        encoding="utf-8",
    )
    model = MockAIModel(check_answers_path=fixture_path)
    request = EvidenceRequest(
        camera_event_id=1,
        evidence_type=EvidenceType.FRAME,
        evidence_ref="frame.jpg",
        question="question",
    )

    with pytest.raises(FixtureError, match="Invalid AI check fixture"):
        model.check_event(request)

    assert len(model.errors) == 1
    assert isinstance(model.errors[0], FixtureError)


def test_mock_camera_event_detector_seeds_database(db_session: Session) -> None:
    detector = MockCameraEventDetector(db_session)

    inserted = detector.seed()
    db_session.flush()

    assert inserted == 16
    assert db_session.get(CameraEvent, 101) is not None
    assert db_session.get(CameraEvent, 606) is not None
