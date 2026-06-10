"""SQLAlchemy ORM models for scans and annotations.

The ORM layer describes how Python objects map to PostgreSQL rows. These models
are intentionally small but realistic: scans hold image metadata, annotations
hold user-created labels tied to one scan and one slice.
"""

from datetime import datetime
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Scan(Base):
    """A medical imaging study or simplified volume available for review."""

    __tablename__ = "scans"

    # UUIDs make client-generated links safe and avoid exposing row counts.
    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    # Human-readable title shown in the frontend scan list.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Local path simulates an S3 object key while keeping the demo simple.
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # Modality teaches that MRI, CT, PET, etc. often need different viewers.
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    # The viewer uses this to bound the slice slider.
    num_slices: Mapped[int] = mapped_column(Integer, nullable=False)
    # Audit timestamp helps data teams understand when a study entered the app.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    annotations: Mapped[list["Annotation"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
    )


class Annotation(Base):
    """A label and geometry drawn by a clinician on a specific scan slice."""

    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name="ck_annotation_confidence_score_range"),
        CheckConstraint("review_status IN ('pending', 'approved', 'rejected')", name="ck_annotation_review_status"),
    )

    # Separate UUID lets annotations be shared, updated, or deleted directly.
    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    # Foreign key maintains referential integrity: no annotation without a scan.
    scan_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("scans.id"), nullable=False)
    # Label is the semantic meaning used by radiologists and ML training.
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # Type tells consumers how to interpret coordinates.
    annotation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # JSONB fits variable geometry shapes: boxes, polygons, segment masks, etc.
    coordinates: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Slice index anchors a 2D drawing inside a 3D volume.
    slice_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # A real system would link to a user table; a string keeps this demo focused.
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    # Radiologist confidence helps ML teams weight uncertain labels differently.
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # QA status prevents unreviewed labels from flowing straight into training.
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    # Reviewer stays nullable because new annotations usually start unreviewed.
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Timestamp records when a human review decision was made.
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Free text supports clinical nuance that a label alone cannot capture.
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Created and updated timestamps are essential for audit trails.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    scan: Mapped[Scan] = relationship(back_populates="annotations")
