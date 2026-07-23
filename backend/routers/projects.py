"""Project and label endpoints for product workspaces."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import CocoExportRead, CsvExportRead, DatasetReleaseArtifactRead, DatasetReleaseRead, DatasetReleaseRevoke, DatasetReleaseSummaryRead, LabelCreate, LabelRead, LabelUpdate, ProjectCreate, ProjectExportRead, ProjectRead, ProjectStatsRead, ProjectUpdate, ScanRead, SegmentationExportRead, YoloExportRead
from ..security import get_current_user, require_admin
from ..services import dataset_release_service, project_service, scan_service
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


@router.get("/projects/{project_id}/releases", response_model=list[DatasetReleaseSummaryRead])
async def list_dataset_releases(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DatasetReleaseSummaryRead]:
    """List immutable releases for one organization-scoped project."""

    return dataset_release_service.list_releases(db, project_id, current_user)


@router.post("/projects/{project_id}/releases", response_model=DatasetReleaseRead, status_code=201)
async def create_dataset_release(
    request: Request,
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DatasetReleaseRead:
    """Snapshot ready scans and approved annotations into an immutable release."""

    release = dataset_release_service.create_release(db, project_id, current_user)
    mark_request_target(request, release["id"], release_version=release["version"])
    return release


@router.get("/dataset-releases/{release_id}", response_model=DatasetReleaseRead)
async def get_dataset_release(
    release_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatasetReleaseRead:
    """Return one stable release manifest without private storage paths."""

    return dataset_release_service.get_release(db, release_id, current_user)


@router.post("/dataset-releases/{release_id}/artifact", response_model=DatasetReleaseArtifactRead)
async def materialize_dataset_release_artifact(
    request: Request,
    release_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DatasetReleaseArtifactRead:
    """Idempotently create a retained artifact for a pre-existing release."""

    artifact = dataset_release_service.materialize_release_artifact(db, release_id, current_user)
    mark_request_target(request, release_id)
    return artifact


@router.get("/dataset-releases/{release_id}/artifact")
async def download_dataset_release_artifact(
    release_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream integrity-checked bytes through the authenticated API boundary."""

    artifact, content = dataset_release_service.download_release_artifact(db, release_id, current_user)
    file_name = f"medi-release-{str(release_id)[:8]}-{artifact.checksum_sha256[:12]}.json"
    return Response(
        content=content,
        media_type=artifact.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "X-Content-SHA256": artifact.checksum_sha256,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/dataset-releases/{release_id}/revoke", response_model=DatasetReleaseRead)
async def revoke_dataset_release(
    request: Request,
    release_id: UUID,
    payload: DatasetReleaseRevoke,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DatasetReleaseRead:
    """Append a controlled revocation event without rewriting the release."""

    release = dataset_release_service.revoke_release(db, release_id, payload.reason_code, current_user)
    mark_request_target(request, release["id"], release_version=release["version"])
    return release


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
