"""Creation and persistence of validated Situations."""

import logging

from sqlalchemy.orm import Session

from app.db.repositories import SituationRepository
from app.db.tables import Situation
from app.domain.validation import validate_situation
from app.ports.ai_model import AIModel

logger = logging.getLogger(__name__)


class SituationService:
    def __init__(
        self,
        ai_model: AIModel,
        situation_repository: SituationRepository,
        session: Session,
    ) -> None:
        self._ai_model = ai_model
        self._situation_repository = situation_repository
        self._session = session

    def create(self, text: str, camera_id: int) -> Situation:
        raw_spec = self._ai_model.create_situation(text)
        spec = validate_situation(raw_spec)
        situation = self._situation_repository.save(text, camera_id, spec)
        self._session.commit()
        logger.info(
            (
                "Created Situation %s for camera %s from %r; Events: %s; "
                "wait_time_seconds=%s; cooldown_seconds=%s"
            ),
            situation.id,
            camera_id,
            text,
            [
                (event.description, event.evidence.value)
                for event in spec.events
            ],
            spec.wait_time_seconds,
            spec.cooldown_seconds,
        )
        return situation
