"""Run the fixture-backed CCTV event analytics demonstration."""

import logging

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
from app.db.session import create_database_engine, create_schema, create_session_factory
from app.db.tables import Alert
from app.domain.models import Answer
from app.ports.ai_model import EvidenceRequest
from app.services.evaluator import Evaluator
from app.services.event_tracker import EventTracker
from app.services.situation_service import SituationService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SCENARIOS = (
    ("Alert me if you see smoke", 1),
    ("Alert me if someone leaves a package at the door and then walks away", 2),
    ("Alert me if you see smoke", 3),
    ("Alert me if someone leaves a package at the door and then walks away", 4),
    ("Alert me if someone leaves a package at the door and then walks away", 5),
    ("Alert me if someone loiters in front of the embassy", 6),
)


def _print_processing_summary(
    camera_events: CameraEventRepository,
    situations: SituationRepository,
    evaluations: EvaluationRepository,
    matches: MatchRepository,
    ai_model: MockAIModel,
) -> None:
    """Print one processing line per Camera Event and applicable Situation."""
    for camera_event in camera_events.list_all_ordered():
        for situation in situations.list_for_camera(camera_event.camera_id):
            evaluation = evaluations.get_for_camera_event_and_situation(
                camera_event.id, situation.id
            )
            if evaluation is None:
                print(
                    f"[{camera_event.timestamp.isoformat()}] camera event "
                    f"{camera_event.id} | Situation {situation.id} | skipped, cooldown"
                )
                continue

            situation_events = situations.list_events(situation.id)
            situation_event = situation_events[evaluation.position]
            result = f"{evaluation.answer.value} {evaluation.confidence:.2f}"
            match = matches.get_for_camera_event_and_situation(
                camera_event.id, situation.id
            )
            if match is not None:
                outcome = (
                    f"advanced {match.position + 1}/{len(situation_events)}"
                )
            else:
                outcome = "no advance"
            request_was_made = any(
                isinstance(call, EvidenceRequest)
                and call.camera_event_id == camera_event.id
                and call.question == situation_event.description
                for call in ai_model.calls
            )
            if not request_was_made:
                raise RuntimeError(
                    f"Evaluation for camera event {camera_event.id} has no AI call"
                )
            print(
                f"[{camera_event.timestamp.isoformat()}] camera event "
                f"{camera_event.id} | Situation {situation.id} | "
                f"Event {evaluation.position + 1} \"{situation_event.description}\" | "
                f"{result} | {outcome}"
            )


def _print_alerts(alerts: AlertRepository) -> None:
    print("\nAlerts")
    for alert in alerts.list_all():
        print(
            f"- Situation {alert.situation_id}, Concrete Situation "
            f"{alert.concrete_situation_id}, created {alert.created_at.isoformat()}: "
            f"{alert.explanation}"
        )


def _print_concrete_situations(
    concrete_situations: ConcreteSituationRepository,
) -> None:
    print("\nConcrete Situations")
    for concrete in concrete_situations.list_all_ordered():
        print(
            f"- {concrete.id}: Situation {concrete.situation_id}, "
            f"{concrete.status.value}, started {concrete.started_at.isoformat()}, "
            f"last match {concrete.last_match_at.isoformat()}"
        )


def main() -> None:
    engine = create_database_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        camera_event_repository = CameraEventRepository(session)
        situation_repository = SituationRepository(session)
        concrete_situation_repository = ConcreteSituationRepository(session)
        match_repository = MatchRepository(session)
        alert_repository = AlertRepository(session)
        evaluation_repository = EvaluationRepository(session)
        handled_repository = HandledCameraEventRepository(session)

        MockCameraEventDetector(session).seed()
        model = MockAIModel()
        situation_service = SituationService(model, situation_repository, session)
        for text, camera_id in SCENARIOS:
            situation_service.create(text, camera_id)

        tracking_model = MockAIModel()
        tracker = EventTracker(
            camera_event_repository=camera_event_repository,
            handled_repository=handled_repository,
            situation_repository=situation_repository,
            concrete_situation_repository=concrete_situation_repository,
            match_repository=match_repository,
            alert_repository=alert_repository,
            evaluation_repository=evaluation_repository,
            evaluator=Evaluator(tracking_model),
            session=session,
        )
        tracker.process_unhandled()
        if tracking_model.errors:
            raise RuntimeError(
                f"Unexpected mock AI errors: {tracking_model.errors!r}"
            )

        _print_processing_summary(
            camera_event_repository,
            situation_repository,
            evaluation_repository,
            match_repository,
            tracking_model,
        )
        _print_alerts(alert_repository)
        _print_concrete_situations(concrete_situation_repository)

    engine.dispose()


if __name__ == "__main__":
    main()
