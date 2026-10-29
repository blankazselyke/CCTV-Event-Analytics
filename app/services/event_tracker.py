"""Sequential processing of unhandled Camera Events."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import CONFIDENCE_THRESHOLD
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
    Match,
)
from app.domain.models import Answer, ConcreteSituationStatus
from app.domain.time import normalize_to_utc
from app.services.evaluator import Evaluator
from app.services.explanation import build_alert_explanation

logger = logging.getLogger(__name__)


class EventTracker:
    def __init__(
        self,
        camera_event_repository: CameraEventRepository,
        handled_repository: HandledCameraEventRepository,
        situation_repository: SituationRepository,
        concrete_situation_repository: ConcreteSituationRepository,
        match_repository: MatchRepository,
        alert_repository: AlertRepository,
        evaluation_repository: EvaluationRepository,
        evaluator: Evaluator,
        session: Session,
    ) -> None:
        self._camera_event_repository = camera_event_repository
        self._handled_repository = handled_repository
        self._situation_repository = situation_repository
        self._concrete_situation_repository = concrete_situation_repository
        self._match_repository = match_repository
        self._alert_repository = alert_repository
        self._evaluation_repository = evaluation_repository
        self._evaluator = evaluator
        self._session = session

    def process(self, camera_event: CameraEvent) -> list[Alert]:
        """Process one persisted Camera Event in its own transaction."""
        with self._camera_event_transaction():
            return self._process_by_id(camera_event.id)

    def process_unhandled(self) -> int:
        """Process all currently unhandled events in timestamp/id order."""
        processed = 0
        while True:
            with self._camera_event_transaction():
                camera_event = self._camera_event_repository.get_earliest_unhandled()
                if camera_event is None:
                    return processed
                self._process_by_id(camera_event.id)
                processed += 1

    def _process_by_id(self, camera_event_id: int) -> list[Alert]:
        alerts: list[Alert] = []
        camera_event = self._camera_event_repository.get(camera_event_id)
        if camera_event is None:
            raise LookupError(f"Camera Event {camera_event_id} does not exist")
        if self._handled_repository.is_handled(camera_event_id):
            return alerts

        for situation in self._situation_repository.list_for_camera(
            camera_event.camera_id
        ):
            situation_events = self._situation_repository.list_events(situation.id)
            if not situation_events:
                raise ValueError(f"Situation {situation.id} has no events")

            concrete = self._concrete_situation_repository.get_open(situation.id)
            if concrete is not None:
                elapsed = (
                    normalize_to_utc(camera_event.timestamp)
                    - normalize_to_utc(concrete.last_match_at)
                ).total_seconds()
                if elapsed > situation.wait_time_seconds:
                    concrete.status = ConcreteSituationStatus.EXPIRED
                    concrete = None
                    logger.info(
                        "Expired Concrete Situation for Situation %s at camera event %s",
                        situation.id,
                        camera_event.id,
                    )

            if concrete is None and self._is_on_cooldown(
                situation.id,
                situation.cooldown_seconds,
                camera_event.timestamp,
            ):
                logger.info(
                    "Skipped Situation %s at camera event %s: cooldown",
                    situation.id,
                    camera_event.id,
                )
                continue

            matches = (
                self._match_repository.list_for_concrete_situation(concrete.id)
                if concrete is not None
                else []
            )
            position = len(matches)
            if position >= len(situation_events):
                raise ValueError(
                    f"Concrete Situation for Situation {situation.id} "
                    "already matched every Event while still open"
                )

            situation_event = situation_events[position]
            result = self._evaluator.check(camera_event, situation_event)
            self._evaluation_repository.add(
                Evaluation(
                    camera_event_id=camera_event.id,
                    situation_id=situation.id,
                    position=position,
                    answer=result.answer,
                    confidence=result.confidence,
                )
            )
            if (
                result.answer is not Answer.YES
                or result.confidence < CONFIDENCE_THRESHOLD
            ):
                continue

            if concrete is None:
                concrete = ConcreteSituation(
                    situation_id=situation.id,
                    status=ConcreteSituationStatus.OPEN,
                    started_at=camera_event.timestamp,
                    last_match_at=camera_event.timestamp,
                )
                self._concrete_situation_repository.add(concrete)
                self._session.flush()

            self._match_repository.add(
                Match(
                    concrete_situation_id=concrete.id,
                    position=position,
                    camera_event_id=camera_event.id,
                    confidence=result.confidence,
                    matched_at=camera_event.timestamp,
                )
            )
            concrete.last_match_at = camera_event.timestamp

            if position == len(situation_events) - 1:
                concrete.status = ConcreteSituationStatus.COMPLETED
                concrete.completed_at = camera_event.timestamp
                completed_matches = [*matches]
                completed_matches.append(
                    Match(
                        concrete_situation_id=concrete.id,
                        position=position,
                        camera_event_id=camera_event.id,
                        confidence=result.confidence,
                        matched_at=camera_event.timestamp,
                    )
                )
                alert = Alert(
                    situation_id=situation.id,
                    description=situation.description,
                    concrete_situation_id=concrete.id,
                    created_at=camera_event.timestamp,
                    explanation=build_alert_explanation(
                        situation_events, completed_matches
                    ),
                )
                self._alert_repository.add(alert)
                alerts.append(alert)

        self._handled_repository.mark_handled(
            camera_event.id, camera_event.timestamp
        )
        return alerts

    @contextmanager
    def _camera_event_transaction(self) -> Iterator[None]:
        transaction = (
            self._session.begin_nested()
            if self._session.in_transaction()
            else self._session.begin()
        )
        with transaction:
            yield

    def _is_on_cooldown(
        self, situation_id: int, cooldown_seconds: int, event_timestamp: datetime
    ) -> bool:
        if cooldown_seconds == 0:
            return False
        latest_completed = self._concrete_situation_repository.get_latest_completed(
            situation_id
        )
        if latest_completed is None or latest_completed.completed_at is None:
            return False
        return (
            normalize_to_utc(latest_completed.completed_at)
            + timedelta(seconds=cooldown_seconds)
            > normalize_to_utc(event_timestamp)
        )
