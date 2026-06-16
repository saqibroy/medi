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
UserRole = Literal["admin", "annotator", "reviewer"]
SourceFormat = Literal["synthetic", "nifti", "dicom", "dicom_zip", "unknown"]
IngestionStatus = Literal["pending", "processing", "ready", "failed"]


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


class AuthTokenRead(BaseModel):
    """Bearer token response used by the browser during Phase 1."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead


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
    created_at: datetime


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


class ExportAnnotationRead(BaseModel):
    """ML-ready annotation row included in a scan export."""

    id: UUID
    label: str
    annotation_type: AnnotationType
    coordinates: dict[str, Any]
    slice_index: int
    confidence_score: float | None
    created_by: str
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
    """COCO bounding-box annotation in image pixel coordinates."""

    id: int
    image_id: int
    category_id: int
    bbox: list[float]
    area: float
    iscrowd: int = 0
    source_annotation_id: UUID


class CocoCategoryRead(BaseModel):
    """COCO category entry derived from project labels."""

    id: int
    name: str


class CocoExportRead(BaseModel):
    """COCO-style export for approved bounding-box annotations."""

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


class ScanStatsRead(BaseModel):
    """Aggregate annotation health metrics for one scan."""

    total_annotations: int
    annotations_by_label: dict[str, int]
    annotations_by_type: dict[str, int]
    annotations_by_status: dict[str, int]
    slices_with_annotations: list[int]
    radiologists_involved: list[str]
