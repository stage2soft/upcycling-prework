from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MappingStrategy(StrEnum):
    FILE_NAME = "file_name"
    JSON_REF_KEY = "json_ref_key"


class MatchStatus(StrEnum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    CONFLICT = "conflict"
    ERROR = "error"


class SelectionStatus(StrEnum):
    PENDING = "pending"
    SELECTED = "selected"
    REJECTED = "rejected"
    MOVE_FAILED = "move_failed"


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    mapping_strategy: Mapped[str] = mapped_column(String(30), default=MappingStrategy.FILE_NAME)
    json_ref_key: Mapped[str] = mapped_column(String(300), default="data_key")
    raw_relative_path: Mapped[str] = mapped_column(Text, default="")
    labeled_relative_path: Mapped[str] = mapped_column(Text, default="")
    paths_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SelectionCandidate(Base):
    __tablename__ = "selection_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    match_key: Mapped[str] = mapped_column(String(500), default="", index=True)
    mapping_strategy: Mapped[str] = mapped_column(String(30))
    match_status: Mapped[str] = mapped_column(String(20), index=True)
    selection_status: Mapped[str] = mapped_column(String(20), default=SelectionStatus.PENDING, index=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    files: Mapped[list[SelectionCandidateFile]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="SelectionCandidateFile.reference_order"
    )


class SelectionCandidateFile(Base):
    __tablename__ = "selection_candidate_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("selection_candidates.id", ondelete="CASCADE"), index=True)
    file_group: Mapped[str] = mapped_column(String(20), index=True)
    reference_order: Mapped[int] = mapped_column(Integer, default=0)
    original_relative_path: Mapped[str] = mapped_column(Text)
    selected_relative_path: Mapped[str] = mapped_column(Text, default="")
    extension: Mapped[str] = mapped_column(String(30), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    mtime: Mapped[float] = mapped_column(Float, default=0)
    is_previewable_image: Mapped[bool] = mapped_column(Boolean, default=False)

    candidate: Mapped[SelectionCandidate] = relationship(back_populates="files")
