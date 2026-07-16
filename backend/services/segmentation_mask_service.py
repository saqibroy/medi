"""Storage and validation for segmentation mask PNGs."""

import base64
import hashlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, AnnotationHistory, Project, Scan, SegmentationMask, User
from .annotation_service import get_annotation_for_user_or_404
from .storage_service import LocalPrivateStorage, mask_key


MASK_STORAGE_ROOT = Path("backend/data/sample_scan/segmentation_masks")
MAX_MASK_BYTES = 15 * 1024 * 1024


def _mask_snapshot(mask: SegmentationMask | None) -> dict | None:
    if mask is None:
        return None
    return {
        "id": str(mask.id),
        "slice_index": mask.slice_index,
        "width": mask.width,
        "height": mask.height,
        "encoding": mask.encoding,
        "byte_size": mask.byte_size,
        "checksum_sha256": mask.checksum_sha256,
    }


def _record_mask_history(annotation: Annotation, current_user: User, action: str, previous: dict | None, new: dict | None) -> AnnotationHistory:
    return AnnotationHistory(
        annotation_id=annotation.id,
        changed_by_user_id=current_user.id,
        action=action,
        changed_fields=["segmentation_mask"],
        previous_values={"segmentation_mask": previous},
        new_values={"segmentation_mask": new},
        created_at=datetime.now(timezone.utc),
    )


def _validate_png_mask(content: bytes, scan: Scan) -> tuple[int, int]:
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mask file is empty")
    if len(content) > MAX_MASK_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mask file exceeds the upload size limit")
    if scan.width is None or scan.height is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scan image dimensions are required for mask upload")

    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            if image.format != "PNG":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Segmentation mask must be a PNG image")
            width, height = image.size
    except UnidentifiedImageError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Segmentation mask must be a PNG image") from error

    if width != scan.width or height != scan.height:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mask dimensions must match scan image dimensions")
    return width, height


def _storage() -> LocalPrivateStorage:
    return LocalPrivateStorage(MASK_STORAGE_ROOT)


def _get_existing_mask(db: Session, annotation_id: UUID, slice_index: int) -> SegmentationMask | None:
    return db.scalar(select(SegmentationMask).where(SegmentationMask.annotation_id == annotation_id, SegmentationMask.slice_index == slice_index))


def _validate_segmentation_annotation(annotation: Annotation, slice_index: int) -> None:
    if annotation.annotation_type != "segmentation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mask upload requires a segmentation annotation")
    if annotation.project_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Segmentation masks require a project-scoped annotation")
    if slice_index != annotation.slice_index:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mask slice must match annotation slice")


def upload_mask_for_user(db: Session, annotation_id: UUID, slice_index: int, content: bytes, current_user: User) -> SegmentationMask:
    """Create or replace a PNG mask for one segmentation annotation slice."""

    if slice_index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    annotation = get_annotation_for_user_or_404(db, annotation_id, current_user)
    _validate_segmentation_annotation(annotation, slice_index)
    scan = db.get(Scan, annotation.scan_id)
    project = db.get(Project, annotation.project_id)
    if scan is None or project is None or scan.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    width, height = _validate_png_mask(content, scan)
    checksum = hashlib.sha256(content).hexdigest()
    storage_key = mask_key(project.organization_id, project.id, scan.id, annotation.id, slice_index)
    _storage().put_bytes(storage_key, content)

    existing_mask = _get_existing_mask(db, annotation.id, slice_index)
    previous = _mask_snapshot(existing_mask)
    if existing_mask is None:
        mask = SegmentationMask(
            annotation_id=annotation.id,
            project_id=project.id,
            scan_id=scan.id,
            slice_index=slice_index,
            storage_key=storage_key,
            width=width,
            height=height,
            byte_size=len(content),
            checksum_sha256=checksum,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        db.add(mask)
    else:
        mask = existing_mask
        mask.storage_key = storage_key
        mask.width = width
        mask.height = height
        mask.byte_size = len(content)
        mask.checksum_sha256 = checksum
        mask.updated_by_user_id = current_user.id

    db.flush()
    db.add(_record_mask_history(annotation, current_user, "mask_uploaded", previous, _mask_snapshot(mask)))
    annotation.updated_by_user_id = current_user.id
    db.commit()
    db.refresh(mask)
    return mask


def get_mask_image_for_user(db: Session, annotation_id: UUID, slice_index: int, current_user: User) -> dict:
    """Return a stored mask as base64 bytes plus metadata."""

    if slice_index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    annotation = get_annotation_for_user_or_404(db, annotation_id, current_user)
    _validate_segmentation_annotation(annotation, slice_index)
    mask = _get_existing_mask(db, annotation.id, slice_index)
    if mask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmentation mask not found")
    storage = _storage()
    if not storage.exists(mask.storage_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmentation mask file not found")
    return {
        "id": mask.id,
        "annotation_id": mask.annotation_id,
        "project_id": mask.project_id,
        "scan_id": mask.scan_id,
        "slice_index": mask.slice_index,
        "width": mask.width,
        "height": mask.height,
        "encoding": mask.encoding,
        "byte_size": mask.byte_size,
        "checksum_sha256": mask.checksum_sha256,
        "created_by_user_id": mask.created_by_user_id,
        "updated_by_user_id": mask.updated_by_user_id,
        "created_at": mask.created_at,
        "updated_at": mask.updated_at,
        "mask_base64": base64.b64encode(storage.get_bytes(mask.storage_key)).decode("ascii"),
    }


def delete_mask_for_user(db: Session, annotation_id: UUID, slice_index: int, current_user: User) -> None:
    """Delete one stored mask after organization and annotation checks."""

    if slice_index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    annotation = get_annotation_for_user_or_404(db, annotation_id, current_user)
    _validate_segmentation_annotation(annotation, slice_index)
    mask = _get_existing_mask(db, annotation.id, slice_index)
    if mask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmentation mask not found")
    _storage().delete(mask.storage_key)
    db.add(_record_mask_history(annotation, current_user, "mask_deleted", _mask_snapshot(mask), None))
    annotation.updated_by_user_id = current_user.id
    db.delete(mask)
    db.commit()


def delete_mask_files_for_annotation(db: Session, annotation: Annotation) -> None:
    """Remove stored mask bytes before an annotation row is deleted."""

    masks = list(db.scalars(select(SegmentationMask).where(SegmentationMask.annotation_id == annotation.id)))
    for mask in masks:
        _storage().delete(mask.storage_key)
