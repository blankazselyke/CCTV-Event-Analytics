"""Tests for Situation structure validation and defaults."""

import pytest
from pydantic import ValidationError

from app.domain.models import Answer, EvaluatorResult, EventSpec, EvidenceType
from app.domain.validation import InvalidSituationError, validate_situation


def event(description: str = "Smoke is visible", evidence: str = "frame") -> dict[str, str]:
    return {"description": description, "evidence": evidence}


def test_situation_defaults_wait_time_and_single_event_cooldown() -> None:
    situation = validate_situation({"events": [event()]})

    assert situation.wait_time_seconds == 300
    assert situation.cooldown_seconds == 300


def test_situation_defaults_multi_event_cooldown_to_zero() -> None:
    situation = validate_situation({"events": [event(), event("Someone walks away")]})

    assert situation.wait_time_seconds == 300
    assert situation.cooldown_seconds == 0


def test_explicit_cooldown_is_preserved() -> None:
    situation = validate_situation({"events": [event()], "cooldown_seconds": 0})

    assert situation.cooldown_seconds == 0


@pytest.mark.parametrize("wait_time", [20, 300, 600])
def test_wait_time_accepts_inclusive_limits(wait_time: int) -> None:
    situation = validate_situation(
        {"events": [event()], "wait_time_seconds": wait_time}
    )

    assert situation.wait_time_seconds == wait_time


@pytest.mark.parametrize("wait_time", [19, 601])
def test_wait_time_outside_limits_is_rejected(wait_time: int) -> None:
    with pytest.raises(InvalidSituationError, match="wait_time_seconds"):
        validate_situation({"events": [event()], "wait_time_seconds": wait_time})


@pytest.mark.parametrize("cooldown", [0, 300, 1800])
def test_cooldown_accepts_inclusive_limits(cooldown: int) -> None:
    situation = validate_situation(
        {"events": [event()], "cooldown_seconds": cooldown}
    )

    assert situation.cooldown_seconds == cooldown


@pytest.mark.parametrize("cooldown", [-1, 1801])
def test_cooldown_outside_limits_is_rejected(cooldown: int) -> None:
    with pytest.raises(InvalidSituationError, match="cooldown_seconds"):
        validate_situation({"events": [event()], "cooldown_seconds": cooldown})


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"events": []},
        {"events": [{"evidence": "frame"}]},
        {"events": [{"description": "   ", "evidence": "frame"}]},
        {"events": [{"description": "Smoke is visible", "evidence": "image"}]},
        {"events": [event()], "unexpected": True},
    ],
)
def test_invalid_situation_structure_raises_clear_error(value: object) -> None:
    with pytest.raises(InvalidSituationError, match="Invalid Situation"):
        validate_situation(value)


def test_repeated_identical_events_are_allowed() -> None:
    repeated = event("A person is standing in front of the embassy")

    situation = validate_situation({"events": [repeated, repeated, repeated]})

    assert len(situation.events) == 3
    assert all(item.description == repeated["description"] for item in situation.events)


def test_event_spec_and_evaluator_result_parse_domain_enums() -> None:
    situation_event = EventSpec.model_validate(event())
    result = EvaluatorResult.model_validate({"answer": "yes", "confidence": 0.8})

    assert situation_event.evidence is EvidenceType.FRAME
    assert result.answer is Answer.YES
    assert result.confidence == 0.8


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_evaluator_confidence_must_be_between_zero_and_one(confidence: float) -> None:
    with pytest.raises(ValidationError):
        EvaluatorResult.model_validate({"answer": "unsure", "confidence": confidence})
