"""HTTP endpoints for creating, reading, updating, and deleting annotations."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import (
    AnnotationCreate,
    AnnotationHistoryRead,
    AnnotationRead,
    AnnotationReviewUpdate,
    AnnotationType,
    AnnotationUpdate,
    ReviewStatus,
    SegmentationMaskImageRead,
    SegmentationMaskRead,
)
from ..security import get_current_user, require_admin, require_annotator, require_reviewer
from ..services import annotation_service
from ..services import segmentation_mask_service
from ..services.audit_service import mark_request_target


router = APIRouter(prefix="/annotations", tags=["annotations"])


@router.get("", response_model=list[AnnotationRead])
async def list_annotations(
    scan_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnnotationRead]:
    """List annotations globally or filter by scan_id for the active viewer."""

    return annotation_service.list_annotations_for_user(db, current_user, scan_id)


@router.get("/search", response_model=list[AnnotationRead])
async def search_annotations(
    label: str | None = None,
    annotation_type: AnnotationType | None = None,
    review_status: ReviewStatus | None = None,
    created_by: str | None = None,
    min_confidence: float | None = None,
    slice_index_min: int | None = None,
    slice_index_max: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnnotationRead]:
    """Search annotations with filters used during ML dataset curation."""

    return annotation_service.search_annotations(
        db=db,
        current_user=current_user,
        label=label,
        annotation_type=annotation_type,
        review_status=review_status,
        created_by=created_by,
        min_confidence=min_confidence,
        slice_index_min=slice_index_min,
        slice_index_max=slice_index_max,
    )


@router.get("/{annotation_id}", response_model=AnnotationRead)
async def get_annotation(
    annotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnnotationRead:
    """Return one annotation for detail panels or edit forms."""

    return annotation_service.get_annotation_for_user_or_404(db, annotation_id, current_user)


@router.get("/{annotation_id}/history", response_model=list[AnnotationHistoryRead])
async def list_annotation_history(
    annotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnnotationHistoryRead]:
    """Return audit entries for one annotation."""

    return annotation_service.list_annotation_history_for_user(db, annotation_id, current_user)


@router.post("/{annotation_id}/mask", response_model=SegmentationMaskRead, status_code=201)
async def upload_segmentation_mask(
    annotation_id: UUID,
    slice_index: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_annotator),
) -> SegmentationMaskRead:
    """Create or replace a PNG segmentation mask for one annotation slice."""

    content = await file.read()
    return segmentation_mask_service.upload_mask_for_user(db, annotation_id, slice_index, content, current_user)


@router.get("/{annotation_id}/mask/{slice_index}", response_model=SegmentationMaskImageRead)
async def get_segmentation_mask(
    annotation_id: UUID,
    slice_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SegmentationMaskImageRead:
    """Return a stored segmentation mask as base64 PNG bytes."""

    return segmentation_mask_service.get_mask_image_for_user(db, annotation_id, slice_index, current_user)


@router.delete("/{annotation_id}/mask/{slice_index}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segmentation_mask(
    annotation_id: UUID,
    slice_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_annotator),
) -> Response:
    """Delete one segmentation mask without deleting the annotation row."""

    segmentation_mask_service.delete_mask_for_user(db, annotation_id, slice_index, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", response_model=AnnotationRead, status_code=201)
async def create_annotation(
    request: Request,
    payload: AnnotationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_annotator),
) -> AnnotationRead:
    """Create a new annotation after Pydantic validates the request body."""

    annotation = annotation_service.create_annotation_for_user(db, payload, current_user)
    mark_request_target(request, annotation.id)
    return annotation


@router.put("/{annotation_id}", response_model=AnnotationRead)
async def update_annotation(
    annotation_id: UUID,
    payload: AnnotationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_annotator),
) -> AnnotationRead:
    """Update an annotation while preserving unspecified fields."""

    return annotation_service.update_annotation_for_user(db, annotation_id, payload, current_user)


@router.patch("/{annotation_id}/review", response_model=AnnotationRead)
async def review_annotation(
    annotation_id: UUID,
    payload: AnnotationReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer),
) -> AnnotationRead:
    """Record a reviewer decision without replacing the full annotation."""

    return annotation_service.review_annotation_for_user(db, annotation_id, payload, current_user)


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    """Delete an annotation and return an empty 204 response."""

    annotation_service.delete_annotation_for_user(db, annotation_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
