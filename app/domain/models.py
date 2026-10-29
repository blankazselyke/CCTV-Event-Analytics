"""Pydantic models for the application's domain."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.config import (
    DEFAULT_MULTI_EVENT_COOLDOWN_SECONDS,
    DEFAULT_SINGLE_EVENT_COOLDOWN_SECONDS,
    DEFAULT_WAIT_TIME_SECONDS,
    MAX_COOLDOWN_SECONDS,
    MAX_WAIT_TIME_SECONDS,
    MIN_COOLDOWN_SECONDS,
    MIN_WAIT_TIME_SECONDS,
)


class EvidenceType(StrEnum):
    """Evidence source required to evaluate a Situation event."""

    FRAME = "frame"
    VIDEO = "video"


class Answer(StrEnum):
    """Possible outcomes from an evaluator."""

    YES = "yes"
    NO = "no"
    UNSURE = "unsure"


class ConcreteSituationStatus(StrEnum):
    """Lifecycle states for one run of a Situation."""

    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


NonEmptyDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class EventSpec(BaseModel):
    """One condition in an ordered Situation."""

    model_config = ConfigDict(extra="forbid")

    description: NonEmptyDescription
    evidence: EvidenceType


class SituationSpec(BaseModel):
    """Validated structure returned when creating a Situation."""

    model_config = ConfigDict(extra="forbid")

    events: list[EventSpec] = Field(min_length=1)
    wait_time_seconds: int = Field(
        default=DEFAULT_WAIT_TIME_SECONDS,
        ge=MIN_WAIT_TIME_SECONDS,
        le=MAX_WAIT_TIME_SECONDS,
    )
    cooldown_seconds: int = Field(
        default=DEFAULT_MULTI_EVENT_COOLDOWN_SECONDS,
        ge=MIN_COOLDOWN_SECONDS,
        le=MAX_COOLDOWN_SECONDS,
    )

    @model_validator(mode="after")
    def apply_event_count_cooldown_default(self) -> Self:
        if "cooldown_seconds" not in self.model_fields_set:
            if len(self.events) == 1:
                self.cooldown_seconds = DEFAULT_SINGLE_EVENT_COOLDOWN_SECONDS
            else:
                self.cooldown_seconds = DEFAULT_MULTI_EVENT_COOLDOWN_SECONDS
        return self


class EvaluatorResult(BaseModel):
    """Answer and confidence returned by the Evaluator."""

    model_config = ConfigDict(extra="forbid")

    answer: Answer
    confidence: float = Field(ge=0.0, le=1.0)
