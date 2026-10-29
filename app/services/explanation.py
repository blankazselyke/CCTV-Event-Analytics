"""Build deterministic Alert explanations from persisted matches."""

from app.db.tables import Match, SituationEvent


def build_alert_explanation(
    situation_events: list[SituationEvent], matches: list[Match]
) -> str:
    events_by_position = {event.position: event for event in situation_events}
    return "; ".join(
        (
            f'Event {match.position + 1} '
            f'"{events_by_position[match.position].description}" matched camera '
            f"event {match.camera_event_id} (confidence {match.confidence:.2f})"
        )
        for match in matches
    )
