"""Business logic for project workspaces and label taxonomies."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, Label, Project, Scan, User
from ..schemas import LabelCreate, LabelUpdate, ProjectCreate, ProjectUpdate


def list_projects(db: Session, current_user: User) -> list[Project]:
    """Return projects visible inside the user's organization."""

    statement = select(Project).where(Project.organization_id == current_user.organization_id).order_by(Project.created_at.desc())
    return list(db.scalars(statement))


def get_project_or_404(db: Session, project_id: UUID, current_user: User) -> Project:
    """Fetch one project and enforce organization scoping."""

    project = db.get(Project, project_id)
    if project is None or project.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def create_project(db: Session, payload: ProjectCreate, current_user: User) -> Project:
    """Create a project in the current user's organization."""

    project = Project(
        organization_id=current_user.organization_id,
        name=payload.name,
        description=payload.description,
        modality=payload.modality,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, project_id: UUID, payload: ProjectUpdate, current_user: User) -> Project:
    """Patch project metadata inside the current user's organization."""

    project = get_project_or_404(db, project_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(project, field_name, value)
    db.commit()
    db.refresh(project)
    return project


def list_project_labels(db: Session, project_id: UUID, current_user: User) -> list[Label]:
    """Return labels for a project."""

    get_project_or_404(db, project_id, current_user)
    statement = select(Label).where(Label.project_id == project_id).order_by(Label.name)
    return list(db.scalars(statement))


def get_label_or_404(db: Session, label_id: UUID, current_user: User) -> Label:
    """Fetch one label and ensure its project belongs to the user's organization."""

    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    get_project_or_404(db, label.project_id, current_user)
    return label


def create_label(db: Session, project_id: UUID, payload: LabelCreate, current_user: User) -> Label:
    """Create a label inside a project taxonomy."""

    get_project_or_404(db, project_id, current_user)
    label = Label(project_id=project_id, name=payload.name, color=payload.color, description=payload.description)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


def update_label(db: Session, label_id: UUID, payload: LabelUpdate, current_user: User) -> Label:
    """Patch a label's display metadata."""

    label = get_label_or_404(db, label_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(label, field_name, value)
    db.commit()
    db.refresh(label)
    return label


def delete_label(db: Session, label_id: UUID, current_user: User) -> None:
    """Delete a label from the project taxonomy."""

    label = get_label_or_404(db, label_id, current_user)
    existing_annotation = db.scalar(select(Annotation).where(Annotation.label_id == label_id).limit(1))
    if existing_annotation is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete a label that is used by annotations")
    db.delete(label)
    db.commit()


def export_project_annotations(db: Session, project_id: UUID, current_user: User) -> dict:
    """Return all scan exports for a project as one dataset payload."""

    project = get_project_or_404(db, project_id, current_user)
    from .scan_service import export_scan_annotations

    scans = list(db.scalars(select(Scan).where(Scan.project_id == project_id).order_by(Scan.created_at.desc())))
    scan_exports = [export_scan_annotations(db, scan.id) for scan in scans]
    return {
        "project_id": project.id,
        "project_name": project.name,
        "export_timestamp": scan_exports[0]["export_timestamp"] if scan_exports else project.created_at,
        "scans": scan_exports,
        "total_annotations": sum(scan_export["total_annotations"] for scan_export in scan_exports),
        "approved_count": sum(scan_export["approved_count"] for scan_export in scan_exports),
        "pending_count": sum(scan_export["pending_count"] for scan_export in scan_exports),
    }


def export_project_coco(db: Session, project_id: UUID, current_user: User) -> dict:
    """Return approved project bounding boxes in COCO format."""

    get_project_or_404(db, project_id, current_user)
    from .export_service import build_coco_export

    scans = list(db.scalars(select(Scan).where(Scan.project_id == project_id).order_by(Scan.created_at.desc())))
    return build_coco_export(db, scans, project_id=project_id)


def export_project_csv(db: Session, project_id: UUID, current_user: User) -> dict:
    """Return project annotations as spreadsheet-friendly CSV."""

    get_project_or_404(db, project_id, current_user)
    from .export_service import build_csv_export

    scans = list(db.scalars(select(Scan).where(Scan.project_id == project_id).order_by(Scan.created_at.desc())))
    return build_csv_export(db, scans, project_id=project_id)


def export_project_yolo(db: Session, project_id: UUID, current_user: User) -> dict:
    """Return approved project bounding boxes in YOLO format."""

    get_project_or_404(db, project_id, current_user)
    from .export_service import build_yolo_export

    scans = list(db.scalars(select(Scan).where(Scan.project_id == project_id).order_by(Scan.created_at.desc())))
    return build_yolo_export(db, scans, project_id=project_id)
