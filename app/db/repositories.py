"""Small repositories that encapsulate database queries."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.db.tables import (
    Alert,
    CameraEvent,
    ConcreteSituation,
    Evaluation,
    HandledCameraEvent,
    Match,
    Situation,
    SituationEvent,
)
from app.domain.models import ConcreteSituationStatus, SituationSpec
from app.domain.time import normalize_to_utc


class CameraEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, camera_event_id: int) -> CameraEvent | None:
        camera_event = self._session.get(CameraEvent, camera_event_id)
        if camera_event is not None:
            set_committed_value(
                camera_event,
                "timestamp",
                normalize_to_utc(camera_event.timestamp),
            )
        return camera_event

    def get_earliest_unhandled(self) -> CameraEvent | None:
        statement = (
            select(CameraEvent)
            .where(
                ~select(HandledCameraEvent.camera_event_id)
                .where(HandledCameraEvent.camera_event_id == CameraEvent.id)
                .exists()
            )
            .order_by(CameraEvent.timestamp, CameraEvent.id)
            .limit(1)
        )
        camera_event = self._session.scalar(statement)
        if camera_event is not None:
            set_committed_value(
                camera_event,
                "timestamp",
                normalize_to_utc(camera_event.timestamp),
            )
        return camera_event

    def list_all_ordered(self) -> list[CameraEvent]:
        statement = select(CameraEvent).order_by(CameraEvent.timestamp, CameraEvent.id)
        camera_events = list(self._session.scalars(statement))
        for camera_event in camera_events:
            set_committed_value(
                camera_event,
                "timestamp",
                normalize_to_utc(camera_event.timestamp),
            )
        return camera_events

    def list_unhandled_ordered(self) -> list[CameraEvent]:
        statement = (
            select(CameraEvent)
            .where(
                ~select(HandledCameraEvent.camera_event_id)
                .where(HandledCameraEvent.camera_event_id == CameraEvent.id)
                .exists()
            )
            .order_by(CameraEvent.timestamp, CameraEvent.id)
        )
        camera_events = list(self._session.scalars(statement))
        for camera_event in camera_events:
            set_committed_value(
                camera_event,
                "timestamp",
                normalize_to_utc(camera_event.timestamp),
            )
        return camera_events


class HandledCameraEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def mark_handled(self, camera_event_id: int, handled_at: datetime) -> None:
        self._session.add(
            HandledCameraEvent(camera_event_id=camera_event_id, handled_at=handled_at)
        )

    def is_handled(self, camera_event_id: int) -> bool:
        return self._session.get(HandledCameraEvent, camera_event_id) is not None


class SituationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, situation: Situation) -> None:
        self._session.add(situation)

    def save(
        self, description: str, camera_id: int, spec: SituationSpec
    ) -> Situation:
        situation = Situation(
            description=description,
            camera_id=camera_id,
            wait_time_seconds=spec.wait_time_seconds,
            cooldown_seconds=spec.cooldown_seconds,
        )
        self._session.add(situation)
        self._session.flush()
        self._session.add_all(
            [
                SituationEvent(
                    situation_id=situation.id,
                    position=position,
                    description=event.description,
                    evidence=event.evidence,
                )
                for position, event in enumerate(spec.events)
            ]
        )
        return situation

    def get(self, situation_id: int) -> Situation | None:
        return self._session.get(Situation, situation_id)

    def list_for_camera(self, camera_id: int) -> list[Situation]:
        statement = select(Situation).where(Situation.camera_id == camera_id)
        return list(self._session.scalars(statement))

    def list_events(self, situation_id: int) -> list[SituationEvent]:
        statement = (
            select(SituationEvent)
            .where(SituationEvent.situation_id == situation_id)
            .order_by(SituationEvent.position)
        )
        return list(self._session.scalars(statement))


class ConcreteSituationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, concrete_situation: ConcreteSituation) -> None:
        self._session.add(concrete_situation)

    def list_all_ordered(self) -> list[ConcreteSituation]:
        statement = select(ConcreteSituation).order_by(ConcreteSituation.id)
        return list(self._session.scalars(statement))

    def get_open(self, situation_id: int) -> ConcreteSituation | None:
        statement = select(ConcreteSituation).where(
            ConcreteSituation.situation_id == situation_id,
            ConcreteSituation.status == ConcreteSituationStatus.OPEN,
        )
        return self._session.scalar(statement)

    def get_latest_completed(self, situation_id: int) -> ConcreteSituation | None:
        statement = (
            select(ConcreteSituation)
            .where(
                ConcreteSituation.situation_id == situation_id,
                ConcreteSituation.status == ConcreteSituationStatus.COMPLETED,
            )
            .order_by(ConcreteSituation.completed_at.desc(), ConcreteSituation.id.desc())
            .limit(1)
        )
        return self._session.scalar(statement)


class MatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, match: Match) -> None:
        self._session.add(match)

    def list_for_concrete_situation(
        self, concrete_situation_id: int
    ) -> list[Match]:
        statement = (
            select(Match)
            .where(Match.concrete_situation_id == concrete_situation_id)
            .order_by(Match.position)
        )
        return list(self._session.scalars(statement))

    def get_for_camera_event_and_situation(
        self, camera_event_id: int, situation_id: int
    ) -> Match | None:
        statement = (
            select(Match)
            .join(
                ConcreteSituation,
                Match.concrete_situation_id == ConcreteSituation.id,
            )
            .where(
                Match.camera_event_id == camera_event_id,
                ConcreteSituation.situation_id == situation_id,
            )
        )
        return self._session.scalar(statement)


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, alert: Alert) -> None:
        self._session.add(alert)

    def list_all(self) -> list[Alert]:
        return list(self._session.scalars(select(Alert).order_by(Alert.id)))


class EvaluationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, evaluation: Evaluation) -> None:
        self._session.add(evaluation)

    def get_for_camera_event_and_situation(
        self, camera_event_id: int, situation_id: int
    ) -> Evaluation | None:
        statement = select(Evaluation).where(
            Evaluation.camera_event_id == camera_event_id,
            Evaluation.situation_id == situation_id,
        )
        return self._session.scalar(statement)
