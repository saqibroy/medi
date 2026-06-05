"""Business logic for annotation CRUD and scan-scoped queries."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation
from ..schemas import AnnotationCreate, AnnotationUpdate
from .scan_service import get_scan_or_404


def list_annotations(db: Session, scan_id: UUID | None = None) -> list[Annotation]:
    """Return annotations, optionally filtered to the scan currently open."""

    statement = select(Annotation).order_by(Annotation.created_at.desc())
    if scan_id is not None:
        statement = statement.where(Annotation.scan_id == scan_id)
    return list(db.scalars(statement))


def get_annotation_or_404(db: Session, annotation_id: UUID) -> Annotation:
    """Fetch one annotation or raise a clear 404 for API clients."""

    annotation = db.get(Annotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return annotation


def create_annotation(db: Session, payload: AnnotationCreate) -> Annotation:
    """Validate the scan exists, then persist a new annotation row."""

    scan = get_scan_or_404(db, payload.scan_id)
    if payload.slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")

    annotation = Annotation(**payload.model_dump())
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


def update_annotation(db: Session, annotation_id: UUID, payload: AnnotationUpdate) -> Annotation:
    """Patch editable annotation fields and commit the transaction."""

    annotation = get_annotation_or_404(db, annotation_id)
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(annotation, field_name, value)

    db.commit()
    db.refresh(annotation)
    return annotation


def delete_annotation(db: Session, annotation_id: UUID) -> None:
    """Delete one annotation; no response body is needed for a 204."""

    annotation = get_annotation_or_404(db, annotation_id)
    db.delete(annotation)
    db.commit()
