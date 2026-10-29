"""SQLAlchemy table mappings for the application."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.domain.models import Answer, ConcreteSituationStatus, EvidenceType
from app.domain.time import normalize_to_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        return normalize_to_utc(value) if value is not None else None

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        return normalize_to_utc(value) if value is not None else None


class Base(DeclarativeBase):
    """Base class for SQLAlchemy mappings."""


class CameraEvent(Base):
    __tablename__ = "camera_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    frame_ref: Mapped[str] = mapped_column(String, nullable=False)
    video_ref: Mapped[str] = mapped_column(String, nullable=False)


class HandledCameraEvent(Base):
    __tablename__ = "handled_camera_events"

    camera_event_id: Mapped[int] = mapped_column(
        ForeignKey("camera_events.id"), primary_key=True
    )
    handled_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class Situation(Base):
    __tablename__ = "situations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    camera_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    wait_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)


class SituationEvent(Base):
    __tablename__ = "situation_events"

    situation_id: Mapped[int] = mapped_column(
        ForeignKey("situations.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[EvidenceType] = mapped_column(
        SqlEnum(EvidenceType, native_enum=False, values_callable=_enum_values),
        nullable=False,
    )


class ConcreteSituation(Base):
    __tablename__ = "concrete_situations"
    __table_args__ = (
        Index(
            "uq_concrete_situations_one_open_per_situation",
            "situation_id",
            unique=True,
            sqlite_where=text("status = 'OPEN'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    situation_id: Mapped[int] = mapped_column(
        ForeignKey("situations.id"), nullable=False, index=True
    )
    status: Mapped[ConcreteSituationStatus] = mapped_column(
        SqlEnum(
            ConcreteSituationStatus,
            native_enum=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_match_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint(
            "concrete_situation_id",
            "camera_event_id",
            name="uq_matches_concrete_situation_camera_event",
        ),
    )

    concrete_situation_id: Mapped[int] = mapped_column(
        ForeignKey("concrete_situations.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_event_id: Mapped[int] = mapped_column(
        ForeignKey("camera_events.id"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    matched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "concrete_situation_id", name="uq_alerts_concrete_situation"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    situation_id: Mapped[int] = mapped_column(ForeignKey("situations.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    concrete_situation_id: Mapped[int] = mapped_column(
        ForeignKey("concrete_situations.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint(
            "camera_event_id",
            "situation_id",
            name="uq_evaluations_camera_event_situation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_event_id: Mapped[int] = mapped_column(
        ForeignKey("camera_events.id"), nullable=False
    )
    situation_id: Mapped[int] = mapped_column(ForeignKey("situations.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    answer: Mapped[Answer] = mapped_column(
        SqlEnum(Answer, native_enum=False, values_callable=_enum_values),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
