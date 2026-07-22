"""Business logic for annotation CRUD and scan-scoped queries."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import Annotation, AnnotationHistory, Label, Project, Scan, User
from ..schemas import AnnotationCreate, AnnotationReviewUpdate, AnnotationUpdate, AnnotationType, ReviewStatus
from .geometry_validation import validate_annotation_geometry
from .scan_service import get_scan_or_404, require_scan_ready


AUDITED_UPDATE_FIELDS = (
    "project_id",
    "label_id",
    "label",
    "annotation_type",
    "coordinates",
    "slice_index",
    "created_by",
    "confidence_score",
    "review_status",
    "reviewer",
    "reviewed_at",
    "notes",
    "assigned_to_user_id",
)


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
    """Fetch one annotation and enforce organization scoping through its scan."""

    annotation = db.scalar(_organization_scoped_annotations(current_user).where(Annotation.id == annotation_id))
    if annotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return annotation


def _organization_scoped_annotations(current_user: User) -> Select[tuple[Annotation]]:
    """Return an annotation query limited by the scan's project organization."""

    return (
        select(Annotation)
        .join(Scan, Annotation.scan_id == Scan.id)
        .join(Project, Scan.project_id == Project.id)
        .where(Project.organization_id == current_user.organization_id, Scan.ingestion_status == "ready")
    )


def _history_value(value: object) -> object:
    """Convert ORM values to JSON-safe audit payloads."""

    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_history_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _history_value(item) for key, item in value.items()}
    return value


def _audit_changes(annotation: Annotation, updates: dict, changed_by_user: User | None, action: str) -> AnnotationHistory | None:
    previous_values = {}
    new_values = {}

    for field_name, value in updates.items():
        if field_name not in AUDITED_UPDATE_FIELDS:
            continue
        previous = _history_value(getattr(annotation, field_name))
        new = _history_value(value)
        if previous == new:
            continue
        previous_values[field_name] = previous
        new_values[field_name] = new

    if not previous_values:
        return None

    return AnnotationHistory(
        annotation_id=annotation.id,
        changed_by_user_id=changed_by_user.id if changed_by_user is not None else None,
        action=action,
        changed_fields=sorted(previous_values),
        previous_values=previous_values,
        new_values=new_values,
        created_at=datetime.now(timezone.utc),
    )


def _validate_assigned_user(db: Session, assigned_to_user_id: UUID | None, project_id: UUID | None) -> None:
    """Ensure assignment points to an active user in the annotation project organization."""

    if assigned_to_user_id is None:
        return
    assigned_user = db.get(User, assigned_to_user_id)
    if assigned_user is None or not assigned_user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")
    if project_id is None:
        return
    project = db.get(Project, project_id)
    if project is None or assigned_user.organization_id != project.organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned user does not belong to annotation project")


def _validate_references_for_user(
    db: Session,
    current_user: User,
    *,
    project_id: UUID | None = None,
    label_id: UUID | None = None,
    assigned_to_user_id: UUID | None = None,
) -> None:
    """Reject missing and cross-organization references with the same opaque 404."""

    if project_id is not None:
        project = db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == current_user.organization_id,
                Project.lifecycle_status != "deleted",
            )
        )
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if label_id is not None:
        label = db.scalar(
            select(Label)
            .join(Project, Label.project_id == Project.id)
            .where(
                Label.id == label_id,
                Project.organization_id == current_user.organization_id,
                Project.lifecycle_status != "deleted",
            )
        )
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    if assigned_to_user_id is not None:
        assigned_user = db.scalar(
            select(User).where(
                User.id == assigned_to_user_id,
                User.organization_id == current_user.organization_id,
                User.is_active.is_(True),
            )
        )
        if assigned_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")


def list_annotations_for_user(db: Session, current_user: User, scan_id: UUID | None = None) -> list[Annotation]:
    """Return annotations visible to the signed-in user's organization."""

    statement = _organization_scoped_annotations(current_user).order_by(Annotation.created_at.desc())
    if scan_id is not None:
        statement = statement.where(Annotation.scan_id == scan_id)
    return list(db.scalars(statement))


def create_annotation(db: Session, payload: AnnotationCreate) -> Annotation:
    """Validate the scan exists, then persist a new annotation row."""

    scan = require_scan_ready(get_scan_or_404(db, payload.scan_id))
    validate_annotation_geometry(scan, payload.annotation_type, payload.coordinates, payload.slice_index)
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
    _validate_assigned_user(db, payload.assigned_to_user_id, annotation_data["project_id"])
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
    _validate_references_for_user(
        db,
        current_user,
        project_id=payload.project_id,
        label_id=payload.label_id,
        assigned_to_user_id=payload.assigned_to_user_id,
    )
    if payload.assigned_to_user_id is None:
        payload = payload.model_copy(update={"assigned_to_user_id": current_user.id})
    return create_annotation(db, payload)


def update_annotation(db: Session, annotation_id: UUID, payload: AnnotationUpdate, changed_by_user: User | None = None) -> Annotation:
    """Patch editable annotation fields and commit the transaction."""

    annotation = get_annotation_or_404(db, annotation_id)
    updates = payload.model_dump(exclude_unset=True)
    scan = require_scan_ready(get_scan_or_404(db, annotation.scan_id))
    if "project_id" in updates and updates["project_id"] is not None and updates["project_id"] != scan.project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Annotation project does not match scan project")
    project_id = updates.get("project_id") or scan.project_id
    if "label_id" in updates and updates["label_id"] is not None:
        label = db.get(Label, updates["label_id"])
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
        if project_id is not None and label.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Label does not belong to annotation project")
    if "assigned_to_user_id" in updates:
        _validate_assigned_user(db, updates["assigned_to_user_id"], project_id)
    validate_annotation_geometry(
        scan,
        updates.get("annotation_type", annotation.annotation_type),
        updates.get("coordinates", annotation.coordinates),
        updates.get("slice_index", annotation.slice_index),
    )
    history = _audit_changes(annotation, updates, changed_by_user, "updated")
    for field_name, value in updates.items():
        setattr(annotation, field_name, value)
    if changed_by_user is not None:
        annotation.updated_by_user_id = changed_by_user.id
    if history is not None:
        db.add(history)

    db.commit()
    db.refresh(annotation)
    return annotation


def update_annotation_for_user(db: Session, annotation_id: UUID, payload: AnnotationUpdate, current_user: User) -> Annotation:
    """Patch an annotation after checking organization access."""

    get_annotation_for_user_or_404(db, annotation_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    _validate_references_for_user(
        db,
        current_user,
        project_id=updates.get("project_id"),
        label_id=updates.get("label_id"),
        assigned_to_user_id=updates.get("assigned_to_user_id"),
    )
    return update_annotation(db, annotation_id, payload, current_user)


def review_annotation(db: Session, annotation_id: UUID, payload: AnnotationReviewUpdate, changed_by_user: User | None = None) -> Annotation:
    """Record a QA review decision for one annotation.

    A review step exists because labels often become ML training data, and a
    second radiologist or QA reviewer helps prevent uncertain or incorrect
    labels from silently degrading a model.
    """

    annotation = get_annotation_or_404(db, annotation_id)
    reviewed_at = datetime.now(timezone.utc)
    history = _audit_changes(
        annotation,
        {
            "reviewer": payload.reviewer,
            "review_status": payload.review_status,
            "notes": payload.notes,
            "reviewed_at": reviewed_at,
        },
        changed_by_user,
        "reviewed",
    )
    annotation.reviewer = payload.reviewer
    annotation.review_status = payload.review_status
    annotation.notes = payload.notes
    annotation.reviewed_at = reviewed_at
    if history is not None:
        db.add(history)
    db.commit()
    db.refresh(annotation)
    return annotation


def review_annotation_for_user(db: Session, annotation_id: UUID, payload: AnnotationReviewUpdate, current_user: User) -> Annotation:
    """Record a review after checking organization access."""

    annotation = get_annotation_for_user_or_404(db, annotation_id, current_user)
    annotation.reviewed_by_user_id = current_user.id
    return review_annotation(db, annotation_id, payload, current_user)


def list_annotation_history_for_user(db: Session, annotation_id: UUID, current_user: User) -> list[AnnotationHistory]:
    """Return audit entries for one annotation after organization scoping."""

    get_annotation_for_user_or_404(db, annotation_id, current_user)
    statement = select(AnnotationHistory).where(AnnotationHistory.annotation_id == annotation_id).order_by(AnnotationHistory.created_at.asc())
    return list(db.scalars(statement))


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

    statement: Select[tuple[Annotation]] = select(Annotation)
    if current_user is not None:
        statement = _organization_scoped_annotations(current_user)
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
    from .segmentation_mask_service import delete_mask_files_for_annotation

    delete_mask_files_for_annotation(db, annotation)
    db.delete(annotation)
    db.commit()


def delete_annotation_for_user(db: Session, annotation_id: UUID, current_user: User) -> None:
    """Delete an annotation after checking organization access."""

    get_annotation_for_user_or_404(db, annotation_id, current_user)
    delete_annotation(db, annotation_id)
