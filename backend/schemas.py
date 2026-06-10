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
ReviewStatus = Literal["pending", "approved", "rejected"]


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


class ScanRead(ScanBase):
    """Scan response returned to React."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_path: str
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


class AnnotationBase(BaseModel):
    """Fields common to annotation creation, update, and responses."""

    scan_id: UUID
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
    created_at: datetime
    updated_at: datetime


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


class ScanStatsRead(BaseModel):
    """Aggregate annotation health metrics for one scan."""

    total_annotations: int
    annotations_by_label: dict[str, int]
    annotations_by_type: dict[str, int]
    annotations_by_status: dict[str, int]
    slices_with_annotations: list[int]
    radiologists_involved: list[str]
