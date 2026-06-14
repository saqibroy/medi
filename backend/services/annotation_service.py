"""Business logic for annotation CRUD and scan-scoped queries."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, Label, Project, User
from ..schemas import AnnotationCreate, AnnotationReviewUpdate, AnnotationUpdate, AnnotationType, ReviewStatus
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


def get_annotation_for_user_or_404(db: Session, annotation_id: UUID, current_user: User) -> Annotation:
    """Fetch one annotation and enforce organization scoping through its project."""

    annotation = get_annotation_or_404(db, annotation_id)
    if annotation.project_id is not None:
        project = db.get(Project, annotation.project_id)
        if project is None or project.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return annotation


def list_annotations_for_user(db: Session, current_user: User, scan_id: UUID | None = None) -> list[Annotation]:
    """Return annotations visible to the signed-in user's organization."""

    statement = select(Annotation).outerjoin(Project, Annotation.project_id == Project.id).order_by(Annotation.created_at.desc())
    statement = statement.where((Annotation.project_id.is_(None)) | (Project.organization_id == current_user.organization_id))
    if scan_id is not None:
        statement = statement.where(Annotation.scan_id == scan_id)
    return list(db.scalars(statement))


def create_annotation(db: Session, payload: AnnotationCreate) -> Annotation:
    """Validate the scan exists, then persist a new annotation row."""

    scan = get_scan_or_404(db, payload.scan_id)
    if payload.slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    if payload.project_id is not None and scan.project_id is not None and payload.project_id != scan.project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Annotation project does not match scan project")
    if payload.label_id is not None:
        label = db.get(Label, payload.label_id)
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
        if scan.project_id is not None and label.project_id != scan.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Label does not belong to scan project")

    annotation_data = payload.model_dump()
    annotation_data["project_id"] = payload.project_id or scan.project_id
    annotation = Annotation(**annotation_data)
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


def create_annotation_for_user(db: Session, payload: AnnotationCreate, current_user: User) -> Annotation:
    """Create an annotation only when scan and label belong to the user's organization."""

    scan = get_scan_or_404(db, payload.scan_id)
    if scan.project_id is not None:
        project = db.get(Project, scan.project_id)
        if project is None or project.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return create_annotation(db, payload)


def update_annotation(db: Session, annotation_id: UUID, payload: AnnotationUpdate) -> Annotation:
    """Patch editable annotation fields and commit the transaction."""

    annotation = get_annotation_or_404(db, annotation_id)
    updates = payload.model_dump(exclude_unset=True)
    if "label_id" in updates and updates["label_id"] is not None:
        label = db.get(Label, updates["label_id"])
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
        if annotation.project_id is not None and label.project_id != annotation.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Label does not belong to annotation project")
    for field_name, value in updates.items():
        setattr(annotation, field_name, value)

    db.commit()
    db.refresh(annotation)
    return annotation


def update_annotation_for_user(db: Session, annotation_id: UUID, payload: AnnotationUpdate, current_user: User) -> Annotation:
    """Patch an annotation after checking organization access."""

    get_annotation_for_user_or_404(db, annotation_id, current_user)
    return update_annotation(db, annotation_id, payload)


def review_annotation(db: Session, annotation_id: UUID, payload: AnnotationReviewUpdate) -> Annotation:
    """Record a QA review decision for one annotation.

    A review step exists because labels often become ML training data, and a
    second radiologist or QA reviewer helps prevent uncertain or incorrect
    labels from silently degrading a model.
    """

    annotation = get_annotation_or_404(db, annotation_id)
    annotation.reviewer = payload.reviewer
    annotation.review_status = payload.review_status
    annotation.notes = payload.notes
    annotation.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(annotation)
    return annotation


def review_annotation_for_user(db: Session, annotation_id: UUID, payload: AnnotationReviewUpdate, current_user: User) -> Annotation:
    """Record a review after checking organization access."""

    annotation = get_annotation_for_user_or_404(db, annotation_id, current_user)
    annotation.reviewed_by_user_id = current_user.id
    return review_annotation(db, annotation_id, payload)


def search_annotations(
    db: Session,
    current_user: User | None = None,
    label: str | None = None,
    annotation_type: AnnotationType | None = None,
    review_status: ReviewStatus | None = None,
    created_by: str | None = None,
    min_confidence: float | None = None,
    slice_index_min: int | None = None,
    slice_index_max: int | None = None,
) -> list[Annotation]:
    """Find annotations with optional filters for ML dataset curation.

    Flexible search matters because dataset builders rarely want every label at
    once: they might need only approved tumour boxes above 0.8 confidence, only
    one radiologist's work, or a slice range that matches a sampled volume.
    """

    statement = select(Annotation)
    if current_user is not None:
        statement = statement.outerjoin(Project, Annotation.project_id == Project.id).where(
            (Annotation.project_id.is_(None)) | (Project.organization_id == current_user.organization_id)
        )
    if label is not None:
        statement = statement.where(Annotation.label == label)
    if annotation_type is not None:
        statement = statement.where(Annotation.annotation_type == annotation_type)
    if review_status is not None:
        statement = statement.where(Annotation.review_status == review_status)
    if created_by is not None:
        statement = statement.where(Annotation.created_by == created_by)
    if min_confidence is not None:
        statement = statement.where(Annotation.confidence_score >= min_confidence)
    if slice_index_min is not None:
        statement = statement.where(Annotation.slice_index >= slice_index_min)
    if slice_index_max is not None:
        statement = statement.where(Annotation.slice_index <= slice_index_max)

    statement = statement.order_by(Annotation.scan_id, Annotation.slice_index, Annotation.created_at.desc())
    return list(db.scalars(statement))


def delete_annotation(db: Session, annotation_id: UUID) -> None:
    """Delete one annotation; no response body is needed for a 204."""

    annotation = get_annotation_or_404(db, annotation_id)
    db.delete(annotation)
    db.commit()


def delete_annotation_for_user(db: Session, annotation_id: UUID, current_user: User) -> None:
    """Delete an annotation after checking organization access."""

    get_annotation_for_user_or_404(db, annotation_id, current_user)
    delete_annotation(db, annotation_id)
