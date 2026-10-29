"""AI model interface used by application services."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import EvaluatorResult, EvidenceType


@dataclass(frozen=True)
class EvidenceRequest:
    """Evidence and question for one Event against one Camera Event."""

    camera_event_id: int
    evidence_type: EvidenceType
    evidence_ref: str
    question: str


class AIModel(Protocol):
    """Port for checking evidence and creating Situation structures."""

    def check_event(self, request: EvidenceRequest) -> EvaluatorResult:
        """Check one Situation Event against one Camera Event."""
        ...

    def create_situation(self, text: str) -> object:
        """Return the raw, untrusted Situation structure for free text."""
        ...
