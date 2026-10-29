"""Fixture-backed mock camera event detector."""

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.db.tables import CameraEvent
from app.domain.time import normalize_to_utc


DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "camera_events.yaml"


class CameraEventFixtureError(ValueError):
    """Raised when camera-event fixture data cannot be loaded."""


class MockCameraEventDetector:
    def __init__(
        self,
        session: Session,
        fixture_path: Path | None = None,
    ) -> None:
        self._session = session
        self._fixture_path = fixture_path or DEFAULT_FIXTURE_PATH

    def seed(self) -> int:
        """Insert all fixture Camera Events into the camera system table."""
        try:
            with self._fixture_path.open(encoding="utf-8") as fixture_file:
                data = yaml.safe_load(fixture_file)
        except OSError as exc:
            raise CameraEventFixtureError(
                f"Could not read camera event fixture {self._fixture_path}: {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise CameraEventFixtureError(
                f"Could not parse camera event fixture {self._fixture_path}: {exc}"
            ) from exc

        if not isinstance(data, dict) or not isinstance(data.get("camera_events"), list):
            raise CameraEventFixtureError(
                "Camera event fixture must contain a 'camera_events' list"
            )

        camera_events = [
            self._parse_camera_event(item, index)
            for index, item in enumerate(data["camera_events"])
        ]
        self._session.add_all(camera_events)
        return len(camera_events)

    @staticmethod
    def _parse_camera_event(value: Any, index: int) -> CameraEvent:
        if not isinstance(value, dict):
            raise CameraEventFixtureError(
                f"Camera event fixture entry {index} must be a mapping"
            )

        try:
            timestamp = normalize_to_utc(datetime.fromisoformat(value["timestamp"]))
            return CameraEvent(
                id=int(value["id"]),
                camera_id=int(value["camera_id"]),
                timestamp=timestamp,
                frame_ref=str(value["frame_ref"]),
                video_ref=str(value["video_ref"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CameraEventFixtureError(
                f"Invalid camera event fixture entry {index}: {exc}"
            ) from exc
