"""Pydantic schemas for request validation and response serialization.

Schemas are the API contract between React and FastAPI. They deliberately mirror
the TypeScript interfaces in frontend/src/types so both sides agree on field
names, types, and validation rules.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


Modality = Literal["MRI", "CT", "PET", "Ultrasound", "XRAY"]
AnnotationType = Literal["bounding_box", "polygon", "segmentation"]
ReviewStatus = Literal["pending", "approved", "rejected", "needs_changes"]
DatasetReleaseStatus = Literal["active", "superseded", "revoked"]
DatasetReleaseAction = Literal["created", "superseded", "revoked"]
DatasetReleaseReason = Literal["quality_issue", "source_withdrawn", "policy_change", "superseded", "other"]
GovernanceScope = Literal["organization", "project", "scan"]
DeletionScope = Literal["project", "scan"]
LegalHoldReason = Literal["litigation", "regulatory", "security_incident", "customer_request"]
DeletionReason = Literal["erasure_request", "source_withdrawal", "contract_end", "duplicate_data"]
UserRole = Literal["admin", "annotator", "reviewer"]
SourceFormat = Literal["synthetic", "nifti", "dicom", "dicom_zip", "unknown"]
IngestionStatus = Literal["pending", "processing", "ready", "failed", "quarantined"]
DeidentificationStatus = Literal["synthetic", "passed", "quarantined", "not_evaluated", "legacy_unverified"]


class UserRead(BaseModel):
    """Signed-in product user returned to the frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    """Email and password accepted by POST /auth/login."""

    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class AuthSessionRead(BaseModel):
    """Browser-safe session response; the opaque credential stays in a cookie."""

    expires_at: datetime
    csrf_token: str
    user: UserRead


class CsrfTokenRead(BaseModel):
    """Signed double-submit token that browser JavaScript may echo in a header."""

    csrf_token: str


class SecurityAuditEventRead(BaseModel):
    """Data-minimized audit event visible only to organization administrators."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    actor_user_id: UUID | None
    actor_session_id: UUID | None
    action: str
    result: Literal["succeeded", "failed", "denied", "error"]
    target_type: str | None
    target_id: UUID | None
    request_id: str | None
    details: dict[str, Any]
    integrity_hash: str
    occurred_at: datetime


class OrganizationRead(BaseModel):
    """Customer workspace metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class ProjectBase(BaseModel):
    """Shared project fields."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)
    modality: Modality


class ProjectCreate(ProjectBase):
    """Payload accepted by POST /projects."""


class ProjectUpdate(BaseModel):
    """Partial project update payload."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)
    modality: Modality | None = None


class ProjectRead(ProjectBase):
    """Project response shown in the workspace selector."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lifecycle_status: Literal["active", "deleted"]
    deleted_at: datetime | None
    created_at: datetime


class DatasetReleaseEventRead(BaseModel):
    """Append-only lifecycle fact attached to a dataset release."""

    id: UUID
    action: DatasetReleaseAction
    reason_code: DatasetReleaseReason | None
    related_release_id: UUID | None
    actor_user_id: UUID
    occurred_at: datetime


class DatasetReleaseSummaryRead(BaseModel):
    """Release metadata safe for project release lists."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    version: int
    schema_version: str
    content_sha256: str
    manifest_sha256: str
    supersedes_release_id: UUID | None
    created_by_user_id: UUID
    created_at: datetime
    status: DatasetReleaseStatus
    lifecycle: list[DatasetReleaseEventRead]


class DatasetReleaseRead(DatasetReleaseSummaryRead):
    """Immutable release metadata and its deterministic manifest."""

    manifest: dict[str, Any]


class DatasetReleaseRevoke(BaseModel):
    """Controlled revocation reason without a free-text PHI channel."""

    reason_code: Literal["quality_issue", "source_withdrawn", "policy_change", "other"]


class DataRetentionPolicyCreate(BaseModel):
    """Explicit organization policy values; no destructive default is assumed."""

    approval_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    original_minimum_days: int = Field(..., ge=0, le=36500)
    mask_minimum_days: int = Field(..., ge=0, le=36500)
    metadata_minimum_days: int = Field(..., ge=0, le=36500)
    dataset_release_minimum_days: int = Field(..., ge=0, le=36500)
    audit_minimum_days: int = Field(..., ge=0, le=36500)
    backup_retention_days: int = Field(..., ge=1, le=36500)
    rpo_hours: int = Field(..., ge=1, le=8760)
    rto_hours: int = Field(..., ge=1, le=8760)


class DataRetentionPolicyRead(DataRetentionPolicyCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    version: int
    created_by_user_id: UUID
    created_at: datetime


class LegalHoldCreate(BaseModel):
    scope_type: GovernanceScope
    scope_id: UUID
    reason_code: LegalHoldReason
    approval_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


class LegalHoldEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: Literal["applied", "released"]
    actor_user_id: UUID
    occurred_at: datetime


class LegalHoldRead(LegalHoldCreate):
    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    created_at: datetime
    status: Literal["active", "released"]
    events: list[LegalHoldEventRead]


class DataDeletionRequestCreate(BaseModel):
    scope_type: DeletionScope
    scope_id: UUID
    reason_code: DeletionReason
    approval_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


class DataDeletionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: Literal["requested", "approved", "cancelled", "executed", "verified", "failed"]
    actor_user_id: UUID
    occurred_at: datetime


class DataDeletionReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    organization_id: UUID
    scope_type: DeletionScope
    scope_id: UUID
    deleted_counts: dict[str, int]
    object_versions_deleted: int
    delete_markers_deleted: int
    revoked_releases: int
    backup_disposition: Literal["expires_per_policy", "not_applicable"]
    backup_expires_at: datetime | None
    approved_by_user_id: UUID
    operator_user_id: UUID
    receipt_sha256: str
    completed_at: datetime


class DataDeletionRequestRead(DataDeletionRequestCreate):
    id: UUID
    organization_id: UUID
    retention_policy_id: UUID
    retention_policy_version: int
    inventory: dict[str, int]
    earliest_execute_at: datetime
    requested_by_user_id: UUID
    created_at: datetime
    status: Literal["requested", "approved", "cancelled", "executed", "verified", "failed"]
    events: list[DataDeletionEventRead]
    receipt: DataDeletionReceiptRead | None


class LabelBase(BaseModel):
    """Shared label fields for project taxonomies."""

    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field("#14b8a6", min_length=4, max_length=20)
    description: str | None = Field(None, max_length=500)


class LabelCreate(LabelBase):
    """Payload accepted by POST /projects/{project_id}/labels."""


class LabelUpdate(BaseModel):
    """Partial label update payload."""

    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, min_length=4, max_length=20)
    description: str | None = Field(None, max_length=500)


class LabelRead(LabelBase):
    """Project label returned to React."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    created_at: datetime


class ScanBase(BaseModel):
    """Shared scan fields used by create and read schemas."""

    name: str = Field(..., min_length=1, max_length=200)
    modality: Modality
    num_slices: int = Field(..., ge=1, description="Number of 2D slices in the volume")


class ScanCreate(ScanBase):
    """Payload accepted by POST /scans.

    The frontend sends metadata and an optional fake file name. Pydantic rejects
    missing names or impossible slice counts before the service touches the DB.
    """

    file_name: str = Field("fake-volume.nii.gz", min_length=1, max_length=255)
    project_id: UUID | None = None


class ScanRead(ScanBase):
    """Scan response returned to React."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None
    source_format: SourceFormat = "synthetic"
    ingestion_status: IngestionStatus = "ready"
    ingestion_error: str | None = None
    deidentification_status: DeidentificationStatus = "not_evaluated"
    deidentification_profile_version: str | None = None
    deidentification_checked_at: datetime | None = None
    deidentification_evidence: dict[str, Any] | None = None
    imaging_metadata: dict[str, Any] | None = None
    width: int | None = None
    height: int | None = None
    depth: int | None = None
    spacing: list[float] | None = None
    window_center: float | None = None
    window_width: float | None = None
    created_at: datetime


class SliceRead(BaseModel):
    """Base64 image payload for the current viewer slice."""

    scan_id: UUID
    slice_index: int
    image_base64: str


class SliceUrlRead(BaseModel):
    """Short-lived authorized URL for one derived preview object."""

    scan_id: UUID
    slice_index: int
    url: str
    expires_in_seconds: int


class SliceDicomMetadataRead(BaseModel):
    """Teaching response that mimics key DICOM metadata for one image slice."""

    scan_id: UUID
    slice_index: int
    PatientID: str
    StudyDate: str
    Modality: Modality
    SliceThickness: float
    PixelSpacing: list[float]
    WindowCenter: int
    WindowLevel: int
    ImageOrientationPatient: list[float]


class ScanMetadataRead(BaseModel):
    """Parsed scan metadata safe to show in the UI."""

    scan_id: UUID
    scan_name: str
    modality: Modality
    source_format: SourceFormat
    ingestion_status: IngestionStatus
    ingestion_error: str | None = None
    deidentification_status: DeidentificationStatus
    deidentification_profile_version: str | None = None
    deidentification_checked_at: datetime | None = None
    deidentification_evidence: dict[str, Any] | None = None
    num_slices: int
    width: int | None = None
    height: int | None = None
    depth: int | None = None
    spacing: list[float] | None = None
    window_center: float | None = None
    window_width: float | None = None
    metadata: dict[str, Any] | None = None


class AnnotationBase(BaseModel):
    """Fields common to annotation creation, update, and responses."""

    scan_id: UUID
    project_id: UUID | None = None
    label_id: UUID | None = None
    label: str = Field(..., min_length=1, max_length=100)
    annotation_type: AnnotationType
    coordinates: dict[str, Any] = Field(
        ...,
        description="Geometry such as {x, y, width, height} for bounding boxes",
    )
    slice_index: int = Field(..., ge=0)
    created_by: str = Field(..., min_length=1, max_length=120)
    confidence_score: float | None = Field(None, ge=0, le=1)
    review_status: ReviewStatus = "pending"
    reviewer: str | None = Field(None, min_length=1, max_length=120)
    reviewed_at: datetime | None = None
    notes: str | None = Field(None, max_length=500)
    assigned_to_user_id: UUID | None = None


class AnnotationCreate(AnnotationBase):
    """Payload accepted by POST /annotations."""


class AnnotationUpdate(BaseModel):
    """Partial payload accepted by PUT /annotations/{annotation_id}.

    Every field is optional so the frontend can update just the geometry after a
    drag operation or just the label after a user edits a form.
    """

    project_id: UUID | None = None
    label_id: UUID | None = None
    label: str | None = Field(None, min_length=1, max_length=100)
    annotation_type: AnnotationType | None = None
    coordinates: dict[str, Any] | None = None
    slice_index: int | None = Field(None, ge=0)
    created_by: str | None = Field(None, min_length=1, max_length=120)
    confidence_score: float | None = Field(None, ge=0, le=1)
    review_status: ReviewStatus | None = None
    reviewer: str | None = Field(None, min_length=1, max_length=120)
    reviewed_at: datetime | None = None
    notes: str | None = Field(None, max_length=500)
    assigned_to_user_id: UUID | None = None


class AnnotationReviewUpdate(BaseModel):
    """Partial review payload accepted by PATCH /annotations/{id}/review.

    Review is separate from geometry editing because production annotation teams
    often let one radiologist draw and another radiologist or QA reviewer decide
    whether the label is trustworthy enough for downstream ML training.
    """

    reviewer: str = Field(..., min_length=1, max_length=120)
    review_status: ReviewStatus
    notes: str | None = Field(None, max_length=500)


class AnnotationRead(AnnotationBase):
    """Annotation response returned to React and ML consumers."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    updated_by_user_id: UUID | None = None
    reviewed_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AnnotationHistoryRead(BaseModel):
    """Append-only audit entry for annotation geometry, label, or review edits."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    annotation_id: UUID
    changed_by_user_id: UUID | None = None
    action: str
    changed_fields: list[str]
    previous_values: dict[str, Any]
    new_values: dict[str, Any]
    created_at: datetime


class SegmentationMaskRead(BaseModel):
    """Metadata for a stored segmentation mask without exposing storage paths."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    annotation_id: UUID
    project_id: UUID
    scan_id: UUID
    slice_index: int
    width: int
    height: int
    encoding: str
    byte_size: int
    checksum_sha256: str
    created_by_user_id: UUID
    updated_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class SegmentationMaskImageRead(SegmentationMaskRead):
    """Stored mask PNG returned as base64 for browser overlay loading."""

    mask_base64: str


class ExportAnnotationRead(BaseModel):
    """ML-ready annotation row included in a scan export."""

    id: UUID
    label: str
    annotation_type: AnnotationType
    coordinates: dict[str, Any]
    slice_index: int
    confidence_score: float | None
    created_by: str
    assigned_to_user_id: UUID | None = None
    review_status: ReviewStatus


class ScanExportRead(BaseModel):
    """Response shape for approved annotations handed to ML pipelines."""

    scan_id: UUID
    scan_name: str
    modality: Modality
    num_slices: int
    export_timestamp: datetime
    annotations: list[ExportAnnotationRead]
    total_annotations: int
    approved_count: int
    pending_count: int


class ProjectExportRead(BaseModel):
    """Project-level export that groups scan exports into one dataset payload."""

    project_id: UUID
    project_name: str
    export_timestamp: datetime
    scans: list[ScanExportRead]
    total_annotations: int
    approved_count: int
    pending_count: int


class CocoImageRead(BaseModel):
    """COCO image entry for one scan slice."""

    id: int
    file_name: str
    width: int
    height: int
    scan_id: UUID
    slice_index: int


class CocoAnnotationRead(BaseModel):
    """COCO annotation in image pixel coordinates."""

    id: int
    image_id: int
    category_id: int
    bbox: list[float]
    area: float
    iscrowd: int = 0
    source_annotation_id: UUID
    annotation_type: AnnotationType
    segmentation: list[list[float]] | None = None


class CocoCategoryRead(BaseModel):
    """COCO category entry derived from project labels."""

    id: int
    name: str


class CocoExportRead(BaseModel):
    """COCO-style export for approved box and polygon annotations."""

    export_format: str = "coco"
    project_id: UUID | None = None
    scan_id: UUID | None = None
    export_timestamp: datetime
    images: list[CocoImageRead]
    annotations: list[CocoAnnotationRead]
    categories: list[CocoCategoryRead]


class YoloFileRead(BaseModel):
    """One YOLO label text file for a scan slice."""

    file_name: str
    scan_id: UUID
    slice_index: int
    image_width: int
    image_height: int
    content: str


class YoloExportRead(BaseModel):
    """YOLO-style export with class names and per-slice label file contents."""

    export_format: str = "yolo"
    project_id: UUID | None = None
    scan_id: UUID | None = None
    export_timestamp: datetime
    classes: list[str]
    files: list[YoloFileRead]


class CsvExportRead(BaseModel):
    """Spreadsheet-friendly CSV export for annotation review."""

    export_format: str = "csv"
    project_id: UUID | None = None
    scan_id: UUID | None = None
    export_timestamp: datetime
    file_name: str
    row_count: int
    content: str


class SegmentationMaskManifestItemRead(BaseModel):
    """One segmentation mask entry for training-data packaging."""

    annotation_id: UUID
    project_id: UUID | None = None
    scan_id: UUID
    scan_name: str
    slice_index: int
    label: str
    review_status: ReviewStatus
    image_width: int
    image_height: int
    mask_available: bool
    mask_file_name: str | None = None
    mask_api_path: str | None = None
    mask_width: int | None = None
    mask_height: int | None = None
    mask_encoding: str | None = None
    mask_byte_size: int | None = None
    mask_checksum_sha256: str | None = None


class SegmentationExportRead(BaseModel):
    """Manifest export for approved segmentation masks."""

    export_format: str = "segmentation_manifest"
    project_id: UUID | None = None
    scan_id: UUID | None = None
    export_timestamp: datetime
    mask_count: int
    available_mask_count: int
    missing_mask_count: int
    masks: list[SegmentationMaskManifestItemRead]


class AnnotationReviewStatsRead(BaseModel):
    """Aggregate annotation health and QA metrics for a scan or project."""

    total_annotations: int
    approved_count: int
    pending_count: int
    rejected_count: int
    needs_changes_count: int
    review_completion_rate: float
    annotations_by_label: dict[str, int]
    annotations_by_type: dict[str, int]
    annotations_by_status: dict[str, int]
    slices_with_annotations: list[int]
    radiologists_involved: list[str]


class ScanStatsRead(AnnotationReviewStatsRead):
    """Aggregate annotation health metrics for one scan."""


class ProjectStatsRead(AnnotationReviewStatsRead):
    """Aggregate annotation health metrics across a project."""

    project_id: UUID
    project_name: str
    scan_count: int
    label_count: int
