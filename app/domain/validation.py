"""Validation helpers for AI-generated Situation structures."""

from pydantic import ValidationError

from app.domain.models import SituationSpec


class InvalidSituationError(ValueError):
    """Raised when an AI-generated Situation does not meet the domain rules."""


def validate_situation(value: object) -> SituationSpec:
    """Validate an untrusted Situation structure and apply its defaults."""
    try:
        return SituationSpec.model_validate(value)
    except ValidationError as exc:
        raise InvalidSituationError(f"Invalid Situation: {exc}") from exc
