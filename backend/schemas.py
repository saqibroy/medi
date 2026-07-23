"""Pydantic schemas for request validation and response serialization.

Schemas are the API contract between React and FastAPI. They deliberately mirror
the TypeScript interfaces in frontend/src/types so both sides agree on field
names, types, and validation rules.
"""

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Modality = Literal["MRI", "CT", "PET", "Ultrasound", "XRAY"]
AnnotationType = Literal["bounding_box", "polygon", "segmentation"]
ReviewStatus = Literal["pending", "approved", "rejected", "needs_changes"]
DatasetReleaseStatus = Literal["active", "superseded", "revoked"]
DatasetReleaseAction = Literal["created", "superseded", "revoked"]
DatasetReleaseReason = Literal["quality_issue", "source_withdrawn", "policy_change", "superseded", "other"]
GovernanceScope = Literal["organization", "project", "scan"]
DeletionScope = GovernanceScope
LegalHoldReason = Literal["litigation", "regulatory", "security_incident", "customer_request"]
DeletionReason = Literal["erasure_request", "source_withdrawal", "contract_end", "duplicate_data"]
UserRole = Literal["admin", "annotator", "reviewer"]
SourceFormat = Literal["synthetic", "nifti", "dicom", "dicom_zip", "unknown"]
IngestionStatus = Literal["pending", "processing", "ready", "failed", "quarantined"]
DeidentificationStatus = Literal["synthetic", "passed", "quarantined", "not_evaluated", "legacy_unverified"]
ExternalAIPurpose = Literal["research_inference", "annotation_assistance", "quality_assurance"]
ExternalAIDataClass = Literal[
    "deidentified_pixels",
    "derived_previews",
    "deidentified_metadata",
    "annotation_geometry",
    "label_taxonomy",
]
ExternalAITransferMechanism = Literal[
    "not_applicable",
    "adequacy_decision",
    "standard_contractual_clauses",
    "approved_derogation",
]
ExternalAIDecisionReason = Literal[
    "authorized",
    "feature_disabled",
    "provider_revoked",
    "provider_unapproved",
    "flow_revoked",
    "flow_unapproved",
    "flow_expired",
    "origin_not_allowlisted",
    "project_unavailable",
    "purpose_not_approved",
    "data_class_not_approved",
    "dataset_not_deidentified",
]
PrivacyOrganizationRole = Literal["controller", "processor", "joint_controller"]
PrivacyPurpose = Literal[
    "research_dataset_annotation",
    "imaging_quality_assurance",
    "ml_dataset_export",
    "security_and_audit",
    "service_operations",
    "customer_support",
    "external_ai_inference",
]
PrivacyLawfulBasis = Literal["consent", "contract", "legal_obligation", "vital_interests", "public_task", "legitimate_interests"]
PrivacyArticle9Condition = Literal[
    "not_applicable",
    "explicit_consent",
    "employment_social_security",
    "vital_interests",
    "nonprofit",
    "made_public",
    "legal_claims",
    "substantial_public_interest",
    "healthcare",
    "public_health",
    "research_statistics",
]
PrivacyTransferMechanism = Literal[
    "not_applicable",
    "adequacy_decision",
    "standard_contractual_clauses",
    "binding_corporate_rules",
    "approved_derogation",
]
PrivacyRequestType = Literal["access", "rectification", "restriction", "objection", "portability", "erasure"]
PrivacyRequestStatus = Literal["received", "identity_verified", "accepted", "fulfilled", "denied", "cancelled", "untracked"]
PrivacyDeadlineStatus = Literal["on_time", "overdue", "completed_on_time", "completed_late"]
PrivacyDenialReason = Literal[
    "identity_not_verified",
    "request_not_applicable",
    "legal_exception",
    "insufficient_scope",
    "manifestly_unfounded_or_excessive",
]
PrivacyOutcome = Literal[
    "secure_delivery",
    "record_corrected",
    "processing_restricted",
    "objection_applied",
    "erasure_verified",
]


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


class ActiveSessionRead(BaseModel):
    """Credential-free active-session metadata visible to administrators."""

    id: UUID
    user_id: UUID
    user_email: str
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    current_session: bool


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


class DatasetReleaseArtifactRead(BaseModel):
    """Safe metadata for one retained private release artifact."""

    id: UUID
    artifact_type: Literal["portable_manifest"]
    schema_version: str
    media_type: str
    object_version_id: str
    checksum_sha256: str
    byte_size: int
    created_by_user_id: UUID
    created_at: datetime


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
    artifacts: list[DatasetReleaseArtifactRead]
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
    target_dispositions: dict[str, Any]
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


class PrivacyProcessingRecordCreate(BaseModel):
    """Controlled processing/DPIA evidence; references point to approved external records."""

    activity_key: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9-]*$")
    organization_role: PrivacyOrganizationRole
    purpose_code: PrivacyPurpose
    lawful_basis: PrivacyLawfulBasis
    health_data_processed: bool
    article9_condition: PrivacyArticle9Condition
    data_subject_categories: list[
        Literal["patients", "research_participants", "workspace_users", "customer_staff", "support_contacts"]
    ] = Field(..., min_length=1, max_length=5)
    personal_data_categories: list[
        Literal[
            "identifiable_medical_images",
            "pseudonymized_medical_images",
            "deidentified_medical_images",
            "annotation_data",
            "account_data",
            "security_audit_data",
            "support_case_data",
        ]
    ] = Field(..., min_length=1, max_length=7)
    recipient_categories: list[
        Literal[
            "authorized_workspace_users",
            "controller_staff",
            "approved_processors",
            "approved_subprocessors",
            "research_collaborators",
            "regulators",
        ]
    ] = Field(..., min_length=1, max_length=6)
    processor_references: list[str] = Field(default_factory=list, max_length=20)
    processing_locations: list[str] = Field(..., min_length=1, max_length=20)
    transfer_mechanism: PrivacyTransferMechanism
    transfer_safeguard_reference: str | None = Field(
        None, min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"
    )
    retention_policy_id: UUID
    security_measure_references: list[str] = Field(..., min_length=1, max_length=20)
    dpia_required: bool
    dpia_outcome: Literal["not_required", "approved", "consultation_required"]
    dpia_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    dpo_review_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    approval_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")

    @field_validator(
        "data_subject_categories",
        "personal_data_categories",
        "recipient_categories",
        "processor_references",
        "processing_locations",
        "security_measure_references",
    )
    @classmethod
    def unique_controlled_values(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for reference in value:
            if not 2 <= len(reference) <= 80 or not all(character.isalnum() or character in "._:/-" for character in reference):
                raise ValueError("list values must be controlled codes or stable references, not free text")
            normalized.append(reference)
        if len(normalized) != len(set(normalized)):
            raise ValueError("list values must not contain duplicates")
        return sorted(normalized)

    @model_validator(mode="after")
    def consistent_legal_evidence(self) -> "PrivacyProcessingRecordCreate":
        if self.health_data_processed == (self.article9_condition == "not_applicable"):
            raise ValueError("health-data processing requires an Article 9 condition; other processing requires not_applicable")
        if self.transfer_mechanism == "not_applicable" and self.transfer_safeguard_reference is not None:
            raise ValueError("transfer_safeguard_reference must be empty when no transfer mechanism applies")
        if self.transfer_mechanism != "not_applicable" and self.transfer_safeguard_reference is None:
            raise ValueError("transfer_safeguard_reference is required for international transfers")
        if self.dpia_required and self.dpia_outcome == "not_required":
            raise ValueError("a required DPIA cannot use the not_required outcome")
        if not self.dpia_required and self.dpia_outcome != "not_required":
            raise ValueError("a non-required DPIA screening must use the not_required outcome")
        return self


class PrivacyProcessingRecordEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: Literal["recorded", "revoked"]
    actor_user_id: UUID
    occurred_at: datetime


class PrivacyProcessingRecordRead(PrivacyProcessingRecordCreate):
    id: UUID
    organization_id: UUID
    version: int
    retention_policy_version: int
    created_by_user_id: UUID
    created_at: datetime
    status: Literal["active", "superseded", "revoked", "consultation_required", "unrecorded"]
    events: list[PrivacyProcessingRecordEventRead]


class PrivacyRequestCreate(BaseModel):
    """Raw subject reference is accepted transiently and returned only as a digest token."""

    case_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    external_subject_reference: str = Field(..., min_length=3, max_length=255)
    request_type: PrivacyRequestType
    scope_type: GovernanceScope
    scope_id: UUID


class PrivacyIdentityVerificationCreate(BaseModel):
    evidence_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


class PrivacyRequestAcceptCreate(BaseModel):
    evidence_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    linked_deletion_request_id: UUID | None = None


class PrivacyRequestFulfillCreate(BaseModel):
    evidence_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    outcome_code: PrivacyOutcome


class PrivacyRequestDenyCreate(BaseModel):
    evidence_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    reason_code: PrivacyDenialReason


class PrivacyRequestCancelCreate(BaseModel):
    evidence_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    reason_code: Literal["requester_withdrew"]


class PrivacyRequestExtendCreate(BaseModel):
    evidence_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    reason_code: Literal["complexity", "request_volume"]


class PrivacyRequestEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: Literal["received", "identity_verified", "accepted", "fulfilled", "denied", "cancelled", "deadline_extended"]
    actor_user_id: UUID
    reason_code: str | None
    outcome_code: PrivacyOutcome | None
    evidence_reference: str | None
    linked_deletion_request_id: UUID | None
    new_due_at: datetime | None
    occurred_at: datetime


class PrivacyRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    case_reference: str
    subject_reference_token: str
    request_type: PrivacyRequestType
    scope_type: GovernanceScope
    scope_id: UUID
    received_at: datetime
    response_due_at: datetime
    effective_due_at: datetime
    created_by_user_id: UUID
    created_at: datetime
    status: PrivacyRequestStatus
    deadline_status: PrivacyDeadlineStatus
    events: list[PrivacyRequestEventRead]


class ExternalAIProviderCreate(BaseModel):
    """Exact provider/model contract snapshot without credentials or free-text data."""

    provider_key: str = Field(..., min_length=2, max_length=60, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(..., min_length=2, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._/-]*$")
    model_name: str = Field(..., min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._:/-]*$")
    model_version: str = Field(..., min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    purpose_code: ExternalAIPurpose
    endpoint_origin: str = Field(..., min_length=9, max_length=255)
    region_code: str = Field(..., min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    data_classes: list[ExternalAIDataClass] = Field(..., min_length=1, max_length=5)
    retention_days: int = Field(..., ge=0, le=3650)
    training_use_allowed: Literal[False] = False
    subprocessors: list[str] = Field(default_factory=list, max_length=20)
    transfer_mechanism: ExternalAITransferMechanism
    contract_owner_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    approval_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")

    @field_validator("endpoint_origin")
    @classmethod
    def exact_https_origin(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("endpoint_origin must be an exact HTTPS origin")
        return normalized

    @field_validator("data_classes")
    @classmethod
    def unique_data_classes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("data_classes must not contain duplicates")
        return sorted(value)

    @field_validator("subprocessors")
    @classmethod
    def safe_subprocessor_references(cls, value: list[str]) -> list[str]:
        normalized = []
        for reference in value:
            if not 2 <= len(reference) <= 80 or not all(character.isalnum() or character in "._:/-" for character in reference):
                raise ValueError("subprocessors must contain stable references, not free text")
            normalized.append(reference)
        if len(normalized) != len(set(normalized)):
            raise ValueError("subprocessors must not contain duplicates")
        return sorted(normalized)


class ExternalAIProviderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: Literal["approved", "revoked"]
    actor_user_id: UUID
    occurred_at: datetime


class ExternalAIProviderRead(ExternalAIProviderCreate):
    id: UUID
    organization_id: UUID
    version: int
    created_by_user_id: UUID
    created_at: datetime
    status: Literal["active", "revoked", "unapproved"]
    events: list[ExternalAIProviderEventRead]


class ExternalAIDataFlowCreate(BaseModel):
    project_id: UUID
    provider_approval_id: UUID
    purpose_code: ExternalAIPurpose
    data_classes: list[ExternalAIDataClass] = Field(..., min_length=1, max_length=5)
    approval_reference: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    expires_at: datetime | None = None

    @field_validator("data_classes")
    @classmethod
    def unique_data_classes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("data_classes must not contain duplicates")
        return sorted(value)


class ExternalAIDataFlowEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: Literal["approved", "revoked"]
    actor_user_id: UUID
    occurred_at: datetime


class ExternalAIDataFlowRead(ExternalAIDataFlowCreate):
    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    created_at: datetime
    status: Literal["active", "revoked", "expired", "unapproved"]
    events: list[ExternalAIDataFlowEventRead]


class ExternalAIEgressEvaluate(BaseModel):
    data_flow_id: UUID
    purpose_code: ExternalAIPurpose
    requested_data_classes: list[ExternalAIDataClass] = Field(..., min_length=1, max_length=5)

    @field_validator("requested_data_classes")
    @classmethod
    def unique_data_classes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("requested_data_classes must not contain duplicates")
        return sorted(value)


class ExternalAIEgressDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    provider_approval_id: UUID
    data_flow_id: UUID
    project_id: UUID
    actor_user_id: UUID
    purpose_code: ExternalAIPurpose
    requested_data_classes: list[ExternalAIDataClass]
    result: Literal["allowed", "denied"]
    reason_code: ExternalAIDecisionReason
    occurred_at: datetime


class ExternalAIStatusRead(BaseModel):
    enabled: bool
    allowed_origins: list[str]
    provider_network_call_implemented: Literal[False] = False
    permanently_prohibited_data_classes: list[str]
