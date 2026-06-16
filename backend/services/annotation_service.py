"""Business logic for annotation CRUD and scan-scoped queries."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, AnnotationHistory, Label, Project, Scan, User
from ..schemas import AnnotationCreate, AnnotationReviewUpdate, AnnotationUpdate, AnnotationType, ReviewStatus
from .scan_service import get_scan_or_404


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
    """Fetch one annotation and enforce organization scoping through its project."""

    annotation = get_annotation_or_404(db, annotation_id)
    if annotation.project_id is not None:
        project = db.get(Project, annotation.project_id)
        if project is None or project.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return annotation


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


def _coordinate_number(coordinates: dict, field_name: str) -> float:
    value = coordinates.get(field_name)
    if not isinstance(value, (int, float)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bounding box coordinates must be numeric")
    return float(value)


def _validate_polygon_geometry(scan: Scan, coordinates: dict) -> None:
    points = coordinates.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon coordinates must include at least three points")

    for point in points:
        if not isinstance(point, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon points must be objects with numeric x and y values")
        x = point.get("x")
        y = point.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon points must be objects with numeric x and y values")
        if x < 0 or y < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon points must be inside image pixel space")
        if scan.width is not None and x > scan.width:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon point exceeds scan image width")
        if scan.height is not None and y > scan.height:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon point exceeds scan image height")


def _validate_annotation_geometry(scan: Scan, annotation_type: str, coordinates: dict, slice_index: int) -> None:
    """Keep annotation geometry in the selected scan's image pixel space."""

    if slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    if annotation_type == "polygon":
        _validate_polygon_geometry(scan, coordinates)
        return
    if annotation_type != "bounding_box":
        return

    x = _coordinate_number(coordinates, "x")
    y = _coordinate_number(coordinates, "y")
    width = _coordinate_number(coordinates, "width")
    height = _coordinate_number(coordinates, "height")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bounding box must have positive image-space dimensions")
    if scan.width is not None and x + width > scan.width:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bounding box exceeds scan image width")
    if scan.height is not None and y + height > scan.height:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bounding box exceeds scan image height")


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
    _validate_annotation_geometry(scan, payload.annotation_type, payload.coordinates, payload.slice_index)
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


def update_annotation(db: Session, annotation_id: UUID, payload: AnnotationUpdate, changed_by_user: User | None = None) -> Annotation:
    """Patch editable annotation fields and commit the transaction."""

    annotation = get_annotation_or_404(db, annotation_id)
    updates = payload.model_dump(exclude_unset=True)
    if "label_id" in updates and updates["label_id"] is not None:
        label = db.get(Label, updates["label_id"])
        if label is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
        if annotation.project_id is not None and label.project_id != annotation.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Label does not belong to annotation project")
    scan = get_scan_or_404(db, annotation.scan_id)
    _validate_annotation_geometry(
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
