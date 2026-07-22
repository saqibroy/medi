"""SQLAlchemy ORM models for scans and annotations.

The ORM layer describes how Python objects map to PostgreSQL rows. These models
are intentionally small but realistic: scans hold image metadata, annotations
hold user-created labels tied to one scan and one slice.
"""

from datetime import datetime
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, event, func
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
    retention_policies: Mapped[list["DataRetentionPolicy"]] = relationship(back_populates="organization", passive_deletes=True)


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
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    """Opaque, revocable session; never stores the raw credential."""

    __tablename__ = "user_sessions"

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now, server_default=func.now(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class SecurityAuditEvent(Base):
    """Append-only, data-minimized record of a security-relevant operation."""

    __tablename__ = "security_audit_events"
    __table_args__ = (
        CheckConstraint("result IN ('succeeded', 'failed', 'denied', 'error')", name="ck_security_audit_event_result"),
        Index("ix_security_audit_events_org_occurred", "organization_id", "occurred_at"),
        Index("ix_security_audit_events_action_occurred", "action", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Actor identifiers intentionally do not cascade or use mutable foreign-key
    # actions: an audit record must survive user/session lifecycle operations.
    actor_user_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_session_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    target_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@event.listens_for(SecurityAuditEvent, "before_update")
@event.listens_for(SecurityAuditEvent, "before_delete")
def _reject_security_audit_event_mutation(*_: object) -> None:
    """Stop normal ORM code from rewriting or deleting audit history."""

    raise ValueError("security audit events are append-only")


class Project(Base):
    """A project groups scans, labels, and review work for one dataset effort."""

    __tablename__ = "projects"

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", server_default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="projects")
    labels: Mapped[list["Label"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    scans: Mapped[list["Scan"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    annotations: Mapped[list["Annotation"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    segmentation_masks: Mapped[list["SegmentationMask"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    dataset_releases: Mapped[list["DatasetRelease"]] = relationship(back_populates="project", passive_deletes=True)


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
    deidentification_status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_evaluated", server_default="not_evaluated")
    deidentification_profile_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deidentification_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deidentification_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    segmentation_masks: Mapped[list["SegmentationMask"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
    )


class Annotation(Base):
    """A label and geometry drawn by a clinician on a specific scan slice."""

    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name="ck_annotation_confidence_score_range"),
        CheckConstraint("review_status IN ('pending', 'approved', 'rejected', 'needs_changes')", name="ck_annotation_review_status"),
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
    assigned_to_user_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
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
    history_entries: Mapped[list["AnnotationHistory"]] = relationship(
        back_populates="annotation",
        cascade="all, delete-orphan",
    )
    segmentation_masks: Mapped[list["SegmentationMask"]] = relationship(
        back_populates="annotation",
        cascade="all, delete-orphan",
    )


class AnnotationHistory(Base):
    """Append-only audit record for annotation edits and review changes."""

    __tablename__ = "annotation_history"

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    annotation_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by_user_id: Mapped[PythonUUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    previous_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    annotation: Mapped[Annotation] = relationship(back_populates="history_entries")


class SegmentationMask(Base):
    """Metadata for a binary segmentation mask stored outside annotation JSON."""

    __tablename__ = "segmentation_masks"
    __table_args__ = (
        UniqueConstraint("annotation_id", "slice_index", name="uq_segmentation_masks_annotation_slice"),
        CheckConstraint("width > 0", name="ck_segmentation_mask_width_positive"),
        CheckConstraint("height > 0", name="ck_segmentation_mask_height_positive"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    annotation_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    scan_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("scans.id"), nullable=False, index=True)
    slice_index: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(700), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    encoding: Mapped[str] = mapped_column(String(40), nullable=False, default="png_binary", server_default="png_binary")
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    annotation: Mapped[Annotation] = relationship(back_populates="segmentation_masks")
    project: Mapped[Project] = relationship(back_populates="segmentation_masks")
    scan: Mapped[Scan] = relationship(back_populates="segmentation_masks")


class DatasetRelease(Base):
    """Immutable, reproducible snapshot of one project's approved dataset."""

    __tablename__ = "dataset_releases"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_dataset_releases_project_version"),
        CheckConstraint("version > 0", name="ck_dataset_release_version_positive"),
        Index("ix_dataset_releases_org_created", "organization_id", "created_at"),
        Index("ix_dataset_releases_project_version", "project_id", "version"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    supersedes_release_id: Mapped[PythonUUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dataset_releases.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped[Project] = relationship(back_populates="dataset_releases", foreign_keys=[project_id])
    lifecycle_events: Mapped[list["DatasetReleaseEvent"]] = relationship(
        back_populates="release",
        foreign_keys="DatasetReleaseEvent.release_id",
        passive_deletes=True,
    )


class DatasetReleaseEvent(Base):
    """Append-only lifecycle fact for release creation, supersession, or revocation."""

    __tablename__ = "dataset_release_events"
    __table_args__ = (
        CheckConstraint("action IN ('created', 'superseded', 'revoked')", name="ck_dataset_release_event_action"),
        CheckConstraint(
            "reason_code IS NULL OR reason_code IN ('quality_issue', 'source_withdrawn', 'policy_change', 'superseded', 'other')",
            name="ck_dataset_release_event_reason",
        ),
        Index("ix_dataset_release_events_release_occurred", "release_id", "occurred_at"),
        Index("ix_dataset_release_events_org_occurred", "organization_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    release_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("dataset_releases.id", ondelete="RESTRICT"), nullable=False)
    organization_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    related_release_id: Mapped[PythonUUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dataset_releases.id", ondelete="RESTRICT"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    release: Mapped[DatasetRelease] = relationship(back_populates="lifecycle_events", foreign_keys=[release_id])


@event.listens_for(DatasetRelease, "before_update")
@event.listens_for(DatasetRelease, "before_delete")
@event.listens_for(DatasetReleaseEvent, "before_update")
@event.listens_for(DatasetReleaseEvent, "before_delete")
def _reject_dataset_release_mutation(*_: object) -> None:
    """Keep release manifests and lifecycle facts append-only through the ORM."""

    raise ValueError("dataset releases are append-only")


class DataRetentionPolicy(Base):
    """Immutable organization policy snapshot with explicitly approved values."""

    __tablename__ = "data_retention_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "version", name="uq_data_retention_policy_org_version"),
        CheckConstraint("version > 0", name="ck_data_retention_policy_version_positive"),
        CheckConstraint("original_minimum_days >= 0", name="ck_retention_original_days"),
        CheckConstraint("mask_minimum_days >= 0", name="ck_retention_mask_days"),
        CheckConstraint("metadata_minimum_days >= 0", name="ck_retention_metadata_days"),
        CheckConstraint("dataset_release_minimum_days >= 0", name="ck_retention_release_days"),
        CheckConstraint("audit_minimum_days >= 0", name="ck_retention_audit_days"),
        CheckConstraint("backup_retention_days > 0", name="ck_retention_backup_days"),
        CheckConstraint("rpo_hours > 0", name="ck_retention_rpo_hours"),
        CheckConstraint("rto_hours > 0", name="ck_retention_rto_hours"),
        Index("ix_data_retention_policies_org_created", "organization_id", "created_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    original_minimum_days: Mapped[int] = mapped_column(Integer, nullable=False)
    mask_minimum_days: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_minimum_days: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_release_minimum_days: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_minimum_days: Mapped[int] = mapped_column(Integer, nullable=False)
    backup_retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    rpo_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    rto_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="retention_policies")


class LegalHold(Base):
    """Immutable legal-hold scope; current state is derived from append-only events."""

    __tablename__ = "legal_holds"
    __table_args__ = (
        CheckConstraint("scope_type IN ('organization', 'project', 'scan')", name="ck_legal_hold_scope"),
        CheckConstraint(
            "reason_code IN ('litigation', 'regulatory', 'security_incident', 'customer_request')",
            name="ck_legal_hold_reason",
        ),
        Index("ix_legal_holds_org_scope", "organization_id", "scope_type", "scope_id"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["LegalHoldEvent"]] = relationship(back_populates="hold", passive_deletes=True)


class LegalHoldEvent(Base):
    """Append-only application or release event for one legal hold."""

    __tablename__ = "legal_hold_events"
    __table_args__ = (
        CheckConstraint("action IN ('applied', 'released')", name="ck_legal_hold_event_action"),
        Index("ix_legal_hold_events_hold_occurred", "hold_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    hold_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("legal_holds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    hold: Mapped[LegalHold] = relationship(back_populates="events")


class DataDeletionRequest(Base):
    """Immutable governed deletion request with a value-free inventory snapshot."""

    __tablename__ = "data_deletion_requests"
    __table_args__ = (
        CheckConstraint("scope_type IN ('project', 'scan')", name="ck_data_deletion_request_scope"),
        CheckConstraint(
            "reason_code IN ('erasure_request', 'source_withdrawal', 'contract_end', 'duplicate_data')",
            name="ck_data_deletion_request_reason",
        ),
        Index("ix_data_deletion_requests_org_created", "organization_id", "created_at"),
        Index("ix_data_deletion_requests_org_scope", "organization_id", "scope_type", "scope_id"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    retention_policy_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("data_retention_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    retention_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    inventory: Mapped[dict] = mapped_column(JSON, nullable=False)
    earliest_execute_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["DataDeletionEvent"]] = relationship(back_populates="request", passive_deletes=True)
    receipt: Mapped["DataDeletionReceipt | None"] = relationship(back_populates="request", uselist=False, passive_deletes=True)


class DataDeletionEvent(Base):
    """Append-only state transition for a governed deletion request."""

    __tablename__ = "data_deletion_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('requested', 'approved', 'cancelled', 'executed', 'verified', 'failed')",
            name="ck_data_deletion_event_action",
        ),
        Index("ix_data_deletion_events_request_occurred", "request_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("data_deletion_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    request: Mapped[DataDeletionRequest] = relationship(back_populates="events")


class DataDeletionReceipt(Base):
    """Append-only, checksum-protected and value-free deletion evidence."""

    __tablename__ = "data_deletion_receipts"
    __table_args__ = (
        CheckConstraint(
            "backup_disposition IN ('expires_per_policy', 'not_applicable')",
            name="ck_data_deletion_receipt_backup_disposition",
        ),
        Index("ix_data_deletion_receipts_org_completed", "organization_id", "completed_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("data_deletion_requests.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    deleted_counts: Mapped[dict] = mapped_column(JSON, nullable=False)
    object_versions_deleted: Mapped[int] = mapped_column(Integer, nullable=False)
    delete_markers_deleted: Mapped[int] = mapped_column(Integer, nullable=False)
    revoked_releases: Mapped[int] = mapped_column(Integer, nullable=False)
    backup_disposition: Mapped[str] = mapped_column(String(30), nullable=False)
    backup_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operator_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    request: Mapped[DataDeletionRequest] = relationship(back_populates="receipt")


class ExternalAIProviderApproval(Base):
    """Immutable approved-provider and exact model-version policy snapshot."""

    __tablename__ = "external_ai_provider_approvals"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider_key", "version", name="uq_external_ai_provider_version"),
        CheckConstraint("version > 0", name="ck_external_ai_provider_version_positive"),
        CheckConstraint(
            "purpose_code IN ('research_inference', 'annotation_assistance', 'quality_assurance')",
            name="ck_external_ai_provider_purpose",
        ),
        CheckConstraint(
            "transfer_mechanism IN ('not_applicable', 'adequacy_decision', 'standard_contractual_clauses', 'approved_derogation')",
            name="ck_external_ai_provider_transfer",
        ),
        CheckConstraint("retention_days >= 0", name="ck_external_ai_provider_retention"),
        CheckConstraint("training_use_allowed = false", name="ck_external_ai_provider_no_training"),
        Index("ix_external_ai_providers_org_created", "organization_id", "created_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    provider_key: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint_origin: Mapped[str] = mapped_column(String(255), nullable=False)
    region_code: Mapped[str] = mapped_column(String(40), nullable=False)
    data_classes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    training_use_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subprocessors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    transfer_mechanism: Mapped[str] = mapped_column(String(40), nullable=False)
    contract_owner_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["ExternalAIProviderEvent"]] = relationship(back_populates="provider", passive_deletes=True)


class ExternalAIProviderEvent(Base):
    """Append-only provider approval or revocation fact."""

    __tablename__ = "external_ai_provider_events"
    __table_args__ = (
        CheckConstraint("action IN ('approved', 'revoked')", name="ck_external_ai_provider_event_action"),
        Index("ix_external_ai_provider_events_provider_occurred", "provider_approval_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider_approval_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("external_ai_provider_approvals.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    provider: Mapped[ExternalAIProviderApproval] = relationship(back_populates="events")


class ExternalAIDataFlowApproval(Base):
    """Immutable project-level approval pinned to one provider policy version."""

    __tablename__ = "external_ai_data_flow_approvals"
    __table_args__ = (
        CheckConstraint(
            "purpose_code IN ('research_inference', 'annotation_assistance', 'quality_assurance')",
            name="ck_external_ai_flow_purpose",
        ),
        Index("ix_external_ai_flows_org_project", "organization_id", "project_id", "created_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    provider_approval_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("external_ai_provider_approvals.id", ondelete="RESTRICT"), nullable=False
    )
    purpose_code: Mapped[str] = mapped_column(String(40), nullable=False)
    data_classes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    provider: Mapped[ExternalAIProviderApproval] = relationship()
    events: Mapped[list["ExternalAIDataFlowEvent"]] = relationship(back_populates="data_flow", passive_deletes=True)


class ExternalAIDataFlowEvent(Base):
    """Append-only project data-flow approval or revocation fact."""

    __tablename__ = "external_ai_data_flow_events"
    __table_args__ = (
        CheckConstraint("action IN ('approved', 'revoked')", name="ck_external_ai_flow_event_action"),
        Index("ix_external_ai_flow_events_flow_occurred", "data_flow_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    data_flow_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("external_ai_data_flow_approvals.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    data_flow: Mapped[ExternalAIDataFlowApproval] = relationship(back_populates="events")


class ExternalAIEgressDecision(Base):
    """Value-free append-only evidence for one governed authorization attempt."""

    __tablename__ = "external_ai_egress_decisions"
    __table_args__ = (
        CheckConstraint("result IN ('allowed', 'denied')", name="ck_external_ai_decision_result"),
        CheckConstraint(
            "reason_code IN ('authorized', 'feature_disabled', 'provider_revoked', 'provider_unapproved', "
            "'flow_revoked', 'flow_unapproved', 'flow_expired', 'origin_not_allowlisted', "
            "'project_unavailable', 'purpose_not_approved', "
            "'data_class_not_approved', 'dataset_not_deidentified')",
            name="ck_external_ai_decision_reason",
        ),
        Index("ix_external_ai_decisions_org_occurred", "organization_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    provider_approval_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("external_ai_provider_approvals.id", ondelete="RESTRICT"), nullable=False
    )
    data_flow_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("external_ai_data_flow_approvals.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_data_classes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PrivacyProcessingRecord(Base):
    """Immutable version of one organization processing activity and DPIA decision."""

    __tablename__ = "privacy_processing_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "activity_key", "version", name="uq_privacy_processing_record_version"),
        CheckConstraint("version > 0", name="ck_privacy_processing_record_version_positive"),
        CheckConstraint(
            "organization_role IN ('controller', 'processor', 'joint_controller')",
            name="ck_privacy_processing_record_role",
        ),
        CheckConstraint(
            "purpose_code IN ('research_dataset_annotation', 'imaging_quality_assurance', 'ml_dataset_export', "
            "'security_and_audit', 'service_operations', 'customer_support', 'external_ai_inference')",
            name="ck_privacy_processing_record_purpose",
        ),
        CheckConstraint(
            "lawful_basis IN ('consent', 'contract', 'legal_obligation', 'vital_interests', "
            "'public_task', 'legitimate_interests')",
            name="ck_privacy_processing_record_lawful_basis",
        ),
        CheckConstraint(
            "article9_condition IN ('not_applicable', 'explicit_consent', 'employment_social_security', "
            "'vital_interests', 'nonprofit', 'made_public', 'legal_claims', "
            "'substantial_public_interest', 'healthcare', 'public_health', 'research_statistics')",
            name="ck_privacy_processing_record_article9",
        ),
        CheckConstraint(
            "(health_data_processed = false AND article9_condition = 'not_applicable') OR "
            "(health_data_processed = true AND article9_condition <> 'not_applicable')",
            name="ck_privacy_processing_record_health_condition",
        ),
        CheckConstraint(
            "transfer_mechanism IN ('not_applicable', 'adequacy_decision', "
            "'standard_contractual_clauses', 'binding_corporate_rules', 'approved_derogation')",
            name="ck_privacy_processing_record_transfer",
        ),
        CheckConstraint(
            "(transfer_mechanism = 'not_applicable' AND transfer_safeguard_reference IS NULL) OR "
            "(transfer_mechanism <> 'not_applicable' AND transfer_safeguard_reference IS NOT NULL)",
            name="ck_privacy_processing_record_transfer_reference",
        ),
        CheckConstraint(
            "dpia_outcome IN ('not_required', 'approved', 'consultation_required')",
            name="ck_privacy_processing_record_dpia_outcome",
        ),
        CheckConstraint(
            "(dpia_required = false AND dpia_outcome = 'not_required') OR "
            "(dpia_required = true AND dpia_outcome IN ('approved', 'consultation_required'))",
            name="ck_privacy_processing_record_dpia_consistency",
        ),
        Index("ix_privacy_processing_records_org_created", "organization_id", "created_at"),
        Index("ix_privacy_processing_records_org_activity", "organization_id", "activity_key", "version"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    activity_key: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_role: Mapped[str] = mapped_column(String(30), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(50), nullable=False)
    lawful_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    health_data_processed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    article9_condition: Mapped[str] = mapped_column(String(50), nullable=False)
    data_subject_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    personal_data_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recipient_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    processor_references: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    processing_locations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    transfer_mechanism: Mapped[str] = mapped_column(String(50), nullable=False)
    transfer_safeguard_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    retention_policy_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_retention_policies.id", ondelete="RESTRICT"), nullable=False
    )
    retention_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    security_measure_references: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dpia_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dpia_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    dpia_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    dpo_review_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["PrivacyProcessingRecordEvent"]] = relationship(
        back_populates="processing_record", passive_deletes=True
    )


class PrivacyProcessingRecordEvent(Base):
    """Append-only record/revocation fact for a processing-activity version."""

    __tablename__ = "privacy_processing_record_events"
    __table_args__ = (
        CheckConstraint("action IN ('recorded', 'revoked')", name="ck_privacy_processing_record_event_action"),
        Index("ix_privacy_processing_record_events_record_occurred", "processing_record_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    processing_record_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("privacy_processing_records.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    processing_record: Mapped[PrivacyProcessingRecord] = relationship(back_populates="events")


class PrivacyRequest(Base):
    """Data-minimized privacy case; the external subject reference is never stored."""

    __tablename__ = "privacy_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "case_reference", name="uq_privacy_request_case_reference"),
        CheckConstraint(
            "request_type IN ('access', 'rectification', 'restriction', 'objection', 'portability', 'erasure')",
            name="ck_privacy_request_type",
        ),
        CheckConstraint("scope_type IN ('organization', 'project', 'scan')", name="ck_privacy_request_scope"),
        Index("ix_privacy_requests_org_created", "organization_id", "created_at"),
        Index("ix_privacy_requests_org_scope", "organization_id", "scope_type", "scope_id"),
        Index("ix_privacy_requests_org_due", "organization_id", "response_due_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    case_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_reference_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    events: Mapped[list["PrivacyRequestEvent"]] = relationship(back_populates="privacy_request", passive_deletes=True)


class PrivacyRequestEvent(Base):
    """Append-only, controlled-value workflow fact for one privacy request."""

    __tablename__ = "privacy_request_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('received', 'identity_verified', 'accepted', 'fulfilled', "
            "'denied', 'cancelled', 'deadline_extended')",
            name="ck_privacy_request_event_action",
        ),
        CheckConstraint(
            "reason_code IS NULL OR reason_code IN ('identity_not_verified', 'request_not_applicable', "
            "'legal_exception', 'insufficient_scope', 'manifestly_unfounded_or_excessive', "
            "'requester_withdrew', 'complexity', 'request_volume')",
            name="ck_privacy_request_event_reason",
        ),
        CheckConstraint(
            "outcome_code IS NULL OR outcome_code IN ('secure_delivery', 'record_corrected', "
            "'processing_restricted', 'objection_applied', 'erasure_verified')",
            name="ck_privacy_request_event_outcome",
        ),
        Index("ix_privacy_request_events_request_occurred", "privacy_request_id", "occurred_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    privacy_request_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("privacy_requests.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[PythonUUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[PythonUUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    outcome_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linked_deletion_request_id: Mapped[PythonUUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_deletion_requests.id", ondelete="RESTRICT"), nullable=True
    )
    new_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    privacy_request: Mapped[PrivacyRequest] = relationship(back_populates="events")


@event.listens_for(DataRetentionPolicy, "before_update")
@event.listens_for(DataRetentionPolicy, "before_delete")
@event.listens_for(LegalHold, "before_update")
@event.listens_for(LegalHold, "before_delete")
@event.listens_for(LegalHoldEvent, "before_update")
@event.listens_for(LegalHoldEvent, "before_delete")
@event.listens_for(DataDeletionRequest, "before_update")
@event.listens_for(DataDeletionRequest, "before_delete")
@event.listens_for(DataDeletionEvent, "before_update")
@event.listens_for(DataDeletionEvent, "before_delete")
@event.listens_for(DataDeletionReceipt, "before_update")
@event.listens_for(DataDeletionReceipt, "before_delete")
@event.listens_for(ExternalAIProviderApproval, "before_update")
@event.listens_for(ExternalAIProviderApproval, "before_delete")
@event.listens_for(ExternalAIProviderEvent, "before_update")
@event.listens_for(ExternalAIProviderEvent, "before_delete")
@event.listens_for(ExternalAIDataFlowApproval, "before_update")
@event.listens_for(ExternalAIDataFlowApproval, "before_delete")
@event.listens_for(ExternalAIDataFlowEvent, "before_update")
@event.listens_for(ExternalAIDataFlowEvent, "before_delete")
@event.listens_for(ExternalAIEgressDecision, "before_update")
@event.listens_for(ExternalAIEgressDecision, "before_delete")
@event.listens_for(PrivacyProcessingRecord, "before_update")
@event.listens_for(PrivacyProcessingRecord, "before_delete")
@event.listens_for(PrivacyProcessingRecordEvent, "before_update")
@event.listens_for(PrivacyProcessingRecordEvent, "before_delete")
@event.listens_for(PrivacyRequest, "before_update")
@event.listens_for(PrivacyRequest, "before_delete")
@event.listens_for(PrivacyRequestEvent, "before_update")
@event.listens_for(PrivacyRequestEvent, "before_delete")
def _reject_data_governance_mutation(*_: object) -> None:
    """Keep lifecycle policies, decisions, and receipts append-only."""

    raise ValueError("data governance records are append-only")
