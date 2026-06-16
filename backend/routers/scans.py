"""HTTP endpoints for scan management and slice retrieval.

The frontend calls these routes to populate the scan list, fetch metadata for a
selected scan, and retrieve a displayable base64 PNG for the current slice.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AnnotationRead, CocoExportRead, CsvExportRead, Modality, ScanCreate, ScanExportRead, ScanMetadataRead, ScanRead, ScanStatsRead, SliceDicomMetadataRead, SliceRead, YoloExportRead
from ..security import get_current_user, require_admin
from ..services import annotation_service, scan_service


router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("", response_model=list[ScanRead])
async def list_scans(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[ScanRead]:
    """List all scans for the React left panel."""

    return scan_service.list_scans(db, current_user=current_user)


@router.get("/{scan_id}", response_model=ScanRead)
async def get_scan(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ScanRead:
    """Return one scan's metadata so the viewer can configure itself."""

    return scan_service.get_scan_for_user_or_404(db, scan_id, current_user)


@router.get("/{scan_id}/slice/{slice_index}", response_model=SliceRead)
async def get_scan_slice(scan_id: UUID, slice_index: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> SliceRead:
    """Return one 2D slice as base64 PNG data.

    Parsed uploads use derived preview PNGs. Seeded and placeholder scans keep a
    generated fallback until they are backed by real imaging files.
    """

    image_base64 = scan_service.get_slice_image_base64_for_user(db, scan_id, slice_index, current_user)
    return SliceRead(scan_id=scan_id, slice_index=slice_index, image_base64=image_base64)


@router.get("/{scan_id}/slice/{slice_index}/metadata", response_model=SliceDicomMetadataRead)
async def get_scan_slice_metadata(scan_id: UUID, slice_index: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> SliceDicomMetadataRead:
    """Return simulated DICOM metadata for one slice."""

    scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return scan_service.get_slice_dicom_metadata(db, scan_id, slice_index)


@router.get("/{scan_id}/metadata", response_model=ScanMetadataRead)
async def get_scan_metadata(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ScanMetadataRead:
    """Return parsed scan metadata safe for the workspace UI."""

    scan = scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return scan_service.get_scan_metadata(scan)


@router.post("", response_model=ScanRead, status_code=201)
async def create_scan(payload: ScanCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ScanRead:
    """Create a fake scan record and placeholder file for local-storage practice."""

    return scan_service.create_scan_for_user(db, payload, current_user)


@router.post("/upload", response_model=ScanRead, status_code=201)
async def upload_scan(
    project_id: UUID = Form(...),
    name: str = Form(...),
    modality: Modality = Form(...),
    num_slices: int = Form(1),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ScanRead:
    """Upload a scan file and create project-scoped scan metadata."""

    content = await file.read()
    return scan_service.create_uploaded_scan_for_user(
        db=db,
        project_id=project_id,
        name=name,
        modality=modality,
        num_slices=num_slices,
        original_filename=file.filename or "uploaded-scan",
        content_type=file.content_type,
        content=content,
        current_user=current_user,
    )


@router.post("/{scan_id}/reprocess", response_model=ScanRead)
async def reprocess_scan(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ScanRead:
    """Retry parsing a failed uploaded scan from its stored original file."""

    return scan_service.reprocess_scan_for_user(db, scan_id, current_user)


@router.get("/{scan_id}/annotations", response_model=list[AnnotationRead])
async def get_scan_annotations(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[AnnotationRead]:
    """Return all annotations for the selected scan."""

    scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return annotation_service.list_annotations_for_user(db, current_user, scan_id)


@router.get("/{scan_id}/export", response_model=ScanExportRead)
async def export_scan_annotations(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ScanExportRead:
    """Return approved annotations in a payload shape useful for ML training."""

    scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return scan_service.export_scan_annotations(db, scan_id)


@router.get("/{scan_id}/export/coco", response_model=CocoExportRead)
async def export_scan_coco(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> CocoExportRead:
    """Return approved scan bounding boxes in COCO format."""

    scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return scan_service.export_scan_coco(db, scan_id)


@router.get("/{scan_id}/export/csv", response_model=CsvExportRead)
async def export_scan_csv(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> CsvExportRead:
    """Return scan annotations as spreadsheet-friendly CSV."""

    scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return scan_service.export_scan_csv(db, scan_id)


@router.get("/{scan_id}/export/yolo", response_model=YoloExportRead)
async def export_scan_yolo(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> YoloExportRead:
    """Return approved scan bounding boxes in YOLO format."""

    scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return scan_service.export_scan_yolo(db, scan_id)


@router.get("/{scan_id}/stats", response_model=ScanStatsRead)
async def get_scan_stats(scan_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ScanStatsRead:
    """Return annotation coverage and QA statistics for a scan."""

    scan_service.get_scan_for_user_or_404(db, scan_id, current_user)
    return scan_service.get_scan_annotation_stats(db, scan_id)
