"""SQLAlchemy ORM models for scans and annotations.

The ORM layer describes how Python objects map to PostgreSQL rows. These models
are intentionally small but realistic: scans hold image metadata, annotations
hold user-created labels tied to one scan and one slice.
"""

from datetime import datetime
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Organization(Base):
    """A customer workspace that owns projects, users, and imaging datasets."""

    __tablename__ = "organizations"

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    projects: Mapped[list["Project"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    """A product user who can annotate, review, or administer a workspace."""

    __tablename__ = "users"

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="annotator", server_default="annotator")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="users")


class Project(Base):
    """A project groups scans, labels, and review work for one dataset effort."""

    __tablename__ = "projects"

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="projects")
    labels: Mapped[list["Label"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    scans: Mapped[list["Scan"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Label(Base):
    """A project-specific semantic class used by annotators and ML exports."""

    __tablename__ = "labels"

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#14b8a6", server_default="#14b8a6")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="labels")
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="label_ref")


class Scan(Base):
    """A medical imaging study or simplified volume available for review."""

    __tablename__ = "scans"

    # UUIDs make client-generated links safe and avoid exposing row counts.
    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    # Human-readable title shown in the frontend scan list.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Local path simulates an S3 object key while keeping the demo simple.
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # Modality teaches that MRI, CT, PET, etc. often need different viewers.
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    # The viewer uses this to bound the slice slider.
    num_slices: Mapped[int] = mapped_column(Integer, nullable=False)
    # Phase 2 ingestion fields keep storage, parser state, and image geometry
    # explicit before real DICOM/NIfTI decoding replaces generated previews.
    storage_key: Mapped[str | None] = mapped_column(String(700), nullable=True)
    source_format: Mapped[str] = mapped_column(String(40), nullable=False, default="synthetic", server_default="synthetic")
    ingestion_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ready", server_default="ready")
    ingestion_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    imaging_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spacing: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    window_center: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Audit timestamp helps data teams understand when a study entered the app.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project | None] = relationship(back_populates="scans")
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
    project_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    # Foreign key maintains referential integrity: no annotation without a scan.
    scan_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("scans.id"), nullable=False)
    label_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("labels.id"), nullable=True)
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
    updated_by_user_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_by_user_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # Created and updated timestamps are essential for audit trails.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    scan: Mapped[Scan] = relationship(back_populates="annotations")
    project: Mapped[Project | None] = relationship(back_populates="annotations")
    label_ref: Mapped[Label | None] = relationship(back_populates="annotations")
