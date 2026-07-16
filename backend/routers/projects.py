"""Project and label endpoints for product workspaces."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import CocoExportRead, CsvExportRead, LabelCreate, LabelRead, LabelUpdate, ProjectCreate, ProjectExportRead, ProjectRead, ProjectStatsRead, ProjectUpdate, ScanRead, SegmentationExportRead, YoloExportRead
from ..security import get_current_user, require_admin
from ..services import project_service, scan_service
from ..services.audit_service import mark_request_target


router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[ProjectRead]:
    """List project workspaces available to the signed-in user's organization."""

    return project_service.list_projects(db, current_user)


@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(
    request: Request,
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ProjectRead:
    """Create a new project workspace."""

    project = project_service.create_project(db, payload, current_user)
    mark_request_target(request, project.id)
    return project


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ProjectRead:
    """Return one project workspace."""

    return project_service.get_project_or_404(db, project_id, current_user)


@router.put("/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ProjectRead:
    """Update a project workspace."""

    return project_service.update_project(db, project_id, payload, current_user)


@router.get("/projects/{project_id}/scans", response_model=list[ScanRead])
async def list_project_scans(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[ScanRead]:
    """List scans inside a project."""

    return scan_service.list_scans(db, project_id=project_id, current_user=current_user)


@router.get("/projects/{project_id}/labels", response_model=list[LabelRead])
async def list_project_labels(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[LabelRead]:
    """List labels inside a project taxonomy."""

    return project_service.list_project_labels(db, project_id, current_user)


@router.get("/projects/{project_id}/export", response_model=ProjectExportRead)
async def export_project(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ProjectExportRead:
    """Export reviewed annotation data across every scan in a project."""

    return project_service.export_project_annotations(db, project_id, current_user)


@router.get("/projects/{project_id}/stats", response_model=ProjectStatsRead)
async def get_project_stats(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ProjectStatsRead:
    """Return project-level annotation coverage and QA statistics."""

    return project_service.get_project_annotation_stats(db, project_id, current_user)


@router.get("/projects/{project_id}/export/coco", response_model=CocoExportRead)
async def export_project_coco(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> CocoExportRead:
    """Export approved project bounding boxes in COCO format."""

    return project_service.export_project_coco(db, project_id, current_user)


@router.get("/projects/{project_id}/export/csv", response_model=CsvExportRead)
async def export_project_csv(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> CsvExportRead:
    """Export project annotations as spreadsheet-friendly CSV."""

    return project_service.export_project_csv(db, project_id, current_user)


@router.get("/projects/{project_id}/export/yolo", response_model=YoloExportRead)
async def export_project_yolo(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> YoloExportRead:
    """Export approved project bounding boxes in YOLO format."""

    return project_service.export_project_yolo(db, project_id, current_user)


@router.get("/projects/{project_id}/export/segmentation", response_model=SegmentationExportRead)
async def export_project_segmentation(project_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> SegmentationExportRead:
    """Export approved project segmentations as a mask manifest."""

    return project_service.export_project_segmentation(db, project_id, current_user)


@router.post("/projects/{project_id}/labels", response_model=LabelRead, status_code=201)
async def create_project_label(
    request: Request,
    project_id: UUID,
    payload: LabelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> LabelRead:
    """Create a label inside a project."""

    label = project_service.create_label(db, project_id, payload, current_user)
    mark_request_target(request, label.id)
    return label


@router.put("/labels/{label_id}", response_model=LabelRead)
async def update_label(
    label_id: UUID,
    payload: LabelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> LabelRead:
    """Update a project label."""

    return project_service.update_label(db, label_id, payload, current_user)


@router.delete("/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(label_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Response:
    """Delete a project label."""

    project_service.delete_label(db, label_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
