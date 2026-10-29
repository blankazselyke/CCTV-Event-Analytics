"""Fixture-backed implementation of the AI model port."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.domain.models import EvaluatorResult
from app.ports.ai_model import EvidenceRequest


DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


class MissingFixtureError(LookupError):
    """Raised when a requested mock model answer has no fixture."""


class FixtureError(ValueError):
    """Raised when a mock model fixture cannot be read or is malformed."""


class MockAIModel:
    def __init__(
        self,
        check_answers_path: Path | None = None,
        situations_path: Path | None = None,
    ) -> None:
        self._check_answers_path = check_answers_path or (
            DEFAULT_FIXTURE_DIR / "ai_check_answers.yaml"
        )
        self._situations_path = situations_path or (
            DEFAULT_FIXTURE_DIR / "ai_situations.yaml"
        )
        self.calls: list[EvidenceRequest | str] = []
        self.errors: list[Exception] = []

    def check_event(self, request: EvidenceRequest) -> EvaluatorResult:
        self.calls.append(request)
        answers = self._load_mapping(self._check_answers_path, "answers")
        event_answers = answers.get(str(request.camera_event_id))
        if not isinstance(event_answers, dict) or request.question not in event_answers:
            error = MissingFixtureError(
                f"No AI check fixture for camera event {request.camera_event_id} "
                f"and question {request.question!r}"
            )
            self.errors.append(error)
            raise error

        fixture = event_answers[request.question]
        if not isinstance(fixture, dict):
            error = FixtureError("AI check fixture entry must be a mapping")
            self.errors.append(error)
            raise error
        if "error" in fixture:
            error = TimeoutError(str(fixture["error"]))
            self.errors.append(error)
            raise error

        try:
            return EvaluatorResult.model_validate(fixture)
        except ValidationError as exc:
            error = FixtureError(f"Invalid AI check fixture: {exc}")
            self.errors.append(error)
            raise error from exc

    def create_situation(self, text: str) -> object:
        self.calls.append(text)
        situations = self._load_mapping(self._situations_path, "situations")
        if text not in situations:
            error = MissingFixtureError(f"No Situation fixture for text {text!r}")
            self.errors.append(error)
            raise error
        return situations[text]

    def _load_mapping(self, path: Path, key: str) -> dict[str, Any]:
        try:
            with path.open(encoding="utf-8") as fixture_file:
                data = yaml.safe_load(fixture_file)
        except OSError as exc:
            error = FixtureError(f"Could not read fixture file {path}: {exc}")
            self.errors.append(error)
            raise error from exc
        except yaml.YAMLError as exc:
            error = FixtureError(f"Could not parse fixture file {path}: {exc}")
            self.errors.append(error)
            raise error from exc

        if not isinstance(data, dict) or not isinstance(data.get(key), dict):
            error = FixtureError(
                f"Fixture file {path} must contain a {key!r} mapping"
            )
            self.errors.append(error)
            raise error
        return data[key]
