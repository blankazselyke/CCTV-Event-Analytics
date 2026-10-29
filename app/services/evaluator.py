"""Evaluation of one Situation Event against one Camera Event."""

import logging

from app.db.tables import CameraEvent, SituationEvent
from app.domain.models import Answer, EvaluatorResult, EvidenceType
from app.ports.ai_model import AIModel, EvidenceRequest

logger = logging.getLogger(__name__)


class Evaluator:
    def __init__(self, ai_model: AIModel) -> None:
        self._ai_model = ai_model

    def check(
        self, camera_event: CameraEvent, situation_event: SituationEvent
    ) -> EvaluatorResult:
        evidence_type = EvidenceType(situation_event.evidence)
        evidence_ref = (
            camera_event.frame_ref
            if evidence_type is EvidenceType.FRAME
            else camera_event.video_ref
        )
        request = EvidenceRequest(
            camera_event_id=camera_event.id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
            question=situation_event.description,
        )
        try:
            result = EvaluatorResult.model_validate(
                self._ai_model.check_event(request)
            )
        except Exception as exc:
            logger.warning(
                "AI evaluation failed for camera event %s and question %r: %s",
                camera_event.id,
                situation_event.description,
                exc,
            )
            return EvaluatorResult(answer=Answer.UNSURE, confidence=0.0)
        return result
