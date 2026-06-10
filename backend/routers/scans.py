"""HTTP endpoints for scan management and slice retrieval.

The frontend calls these routes to populate the scan list, fetch metadata for a
selected scan, and retrieve a displayable base64 PNG for the current slice.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import AnnotationRead, ScanCreate, ScanExportRead, ScanRead, ScanStatsRead, SliceDicomMetadataRead, SliceRead
from ..services import annotation_service, scan_service


router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("", response_model=list[ScanRead])
def list_scans(db: Session = Depends(get_db)) -> list[ScanRead]:
    """List all scans for the React left panel."""

    return scan_service.list_scans(db)


@router.get("/{scan_id}", response_model=ScanRead)
def get_scan(scan_id: UUID, db: Session = Depends(get_db)) -> ScanRead:
    """Return one scan's metadata so the viewer can configure itself."""

    return scan_service.get_scan_or_404(db, scan_id)


@router.get("/{scan_id}/slice/{slice_index}", response_model=SliceRead)
def get_scan_slice(scan_id: UUID, slice_index: int, db: Session = Depends(get_db)) -> SliceRead:
    """Return one fake 2D slice as base64 PNG data.

    This route is sync def because SQLAlchemy and Pillow work synchronously here.
    FastAPI also supports async def for awaitable I/O such as async database
    drivers or HTTP calls; mixing sync libraries inside async endpoints can block
    the event loop, so this teaching project uses plain def where appropriate.
    """

    image_base64 = scan_service.get_slice_image_base64(db, scan_id, slice_index)
    return SliceRead(scan_id=scan_id, slice_index=slice_index, image_base64=image_base64)


@router.get("/{scan_id}/slice/{slice_index}/metadata", response_model=SliceDicomMetadataRead)
def get_scan_slice_metadata(scan_id: UUID, slice_index: int, db: Session = Depends(get_db)) -> SliceDicomMetadataRead:
    """Return simulated DICOM metadata for one slice."""

    return scan_service.get_slice_dicom_metadata(db, scan_id, slice_index)


@router.post("", response_model=ScanRead, status_code=201)
def create_scan(payload: ScanCreate, db: Session = Depends(get_db)) -> ScanRead:
    """Create a fake scan record and placeholder file for local-storage practice."""

    return scan_service.create_scan(db, payload)


@router.get("/{scan_id}/annotations", response_model=list[AnnotationRead])
def get_scan_annotations(scan_id: UUID, db: Session = Depends(get_db)) -> list[AnnotationRead]:
    """Return all annotations for the selected scan."""

    scan_service.get_scan_or_404(db, scan_id)
    return annotation_service.list_annotations(db, scan_id)


@router.get("/{scan_id}/export", response_model=ScanExportRead)
def export_scan_annotations(scan_id: UUID, db: Session = Depends(get_db)) -> ScanExportRead:
    """Return approved annotations in a payload shape useful for ML training."""

    return scan_service.export_scan_annotations(db, scan_id)


@router.get("/{scan_id}/stats", response_model=ScanStatsRead)
def get_scan_stats(scan_id: UUID, db: Session = Depends(get_db)) -> ScanStatsRead:
    """Return annotation coverage and QA statistics for a scan."""

    return scan_service.get_scan_annotation_stats(db, scan_id)
