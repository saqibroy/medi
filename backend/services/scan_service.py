"""Business logic for scan metadata and simulated image slices.

Routers should stay thin: they translate HTTP into service calls. This service
owns scan-specific decisions such as how local storage paths are created and how
fake slice images are generated for the learning viewer.
"""

import base64
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, Project, Scan, User
from ..schemas import ScanCreate
from .imaging_service import ImagingIngestionError, build_initial_scan_profile, build_nifti_scan_profile, detect_source_format


STORAGE_ROOT = Path(__file__).resolve().parents[1] / "data" / "sample_scan"


def list_scans(db: Session, project_id: UUID | None = None, current_user: User | None = None) -> list[Scan]:
    """Return all scans ordered by creation time for the left navigation panel."""

    statement = select(Scan).order_by(Scan.created_at.desc())
    if current_user is not None:
        statement = statement.outerjoin(Project, Scan.project_id == Project.id).where(
            (Scan.project_id.is_(None)) | (Project.organization_id == current_user.organization_id)
        )
    if project_id is not None:
        if current_user is not None:
            project = db.get(Project, project_id)
            if project is None or project.organization_id != current_user.organization_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        statement = statement.where(Scan.project_id == project_id)
    return list(db.scalars(statement))


def get_scan_or_404(db: Session, scan_id: UUID) -> Scan:
    """Fetch one scan or raise an HTTP 404 that FastAPI turns into JSON."""

    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan


def get_scan_for_user_or_404(db: Session, scan_id: UUID, current_user: User) -> Scan:
    """Fetch one scan and ensure it belongs to the user's organization."""

    scan = get_scan_or_404(db, scan_id)
    if scan.project_id is not None:
        project = db.get(Project, scan.project_id)
        if project is None or project.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan


def create_scan(db: Session, payload: ScanCreate) -> Scan:
    """Create fake scan metadata and a placeholder local file."""

    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = payload.file_name.replace("/", "_")
    file_path = STORAGE_ROOT / safe_name
    file_path.write_text("fake volumetric scan data for interview learning\n")
    scan_profile = build_initial_scan_profile("synthetic", payload.modality, payload.num_slices, str(file_path))

    scan = Scan(
        name=payload.name,
        project_id=payload.project_id,
        file_path=str(file_path),
        modality=payload.modality,
        num_slices=payload.num_slices,
        **scan_profile,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def create_scan_for_user(db: Session, payload: ScanCreate, current_user: User) -> Scan:
    """Create a scan only inside a project visible to the signed-in user."""

    if payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is None or project.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return create_scan(db, payload)


def create_uploaded_scan_for_user(
    db: Session,
    project_id: UUID,
    name: str,
    modality: str,
    num_slices: int,
    original_filename: str,
    content: bytes,
    current_user: User,
) -> Scan:
    """Store an uploaded scan file and create project-scoped scan metadata."""

    project = db.get(Project, project_id)
    if project is None or project.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if num_slices < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Number of slices must be at least 1")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    scan_id = uuid4()
    safe_original_name = Path(original_filename or "uploaded-scan").name.replace("/", "_")
    scan_storage_root = STORAGE_ROOT / str(project_id) / str(scan_id)
    original_storage_root = scan_storage_root / "original"
    preview_storage_root = scan_storage_root / "derived" / "preview"
    original_storage_root.mkdir(parents=True, exist_ok=True)
    file_path = original_storage_root / safe_original_name
    file_path.write_bytes(content)
    source_format = detect_source_format(safe_original_name, content)
    try:
        scan_profile = (
            build_nifti_scan_profile(safe_original_name, content, modality, str(scan_storage_root), preview_storage_root)
            if source_format == "nifti"
            else build_initial_scan_profile(source_format, modality, num_slices, str(scan_storage_root))
        )
    except ImagingIngestionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    scan = Scan(
        id=scan_id,
        project_id=project_id,
        name=name,
        file_path=str(file_path),
        modality=modality,
        num_slices=scan_profile["depth"] or num_slices,
        **scan_profile,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def _read_derived_preview_base64(scan: Scan, slice_index: int) -> str | None:
    """Return a derived preview PNG if ingestion generated one."""

    if not scan.storage_key:
        return None
    preview_path = Path(scan.storage_key) / "derived" / "preview" / f"{slice_index:06d}.png"
    if not preview_path.exists():
        return None
    return base64.b64encode(preview_path.read_bytes()).decode("ascii")


def _generate_placeholder_slice_base64(scan: Scan, slice_index: int) -> str:
    """Generate a fallback PNG slice for seeded and placeholder scans."""

    image = Image.new("L", (512, 512), color=18)
    draw = ImageDraw.Draw(image)
    offset = int((slice_index / max(scan.num_slices - 1, 1)) * 120)
    draw.ellipse((120 + offset, 100, 390 - offset // 2, 410), fill=95)
    draw.ellipse((210, 190 + offset // 3, 315, 295 + offset // 3), fill=160)
    draw.text((20, 20), f"{scan.modality} slice {slice_index}", fill=230)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _get_slice_image_base64(scan: Scan, slice_index: int) -> str:
    """Return a derived preview slice or generated fallback image."""

    if slice_index < 0 or slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    return _read_derived_preview_base64(scan, slice_index) or _generate_placeholder_slice_base64(scan, slice_index)


def get_slice_image_base64(db: Session, scan_id: UUID, slice_index: int) -> str:
    """Return a PNG slice as base64 so React can render it."""

    return _get_slice_image_base64(get_scan_or_404(db, scan_id), slice_index)


def get_slice_image_base64_for_user(db: Session, scan_id: UUID, slice_index: int, current_user: User) -> str:
    """Return a slice after checking scan access."""

    return _get_slice_image_base64(get_scan_for_user_or_404(db, scan_id, current_user), slice_index)


def get_slice_dicom_metadata(db: Session, scan_id: UUID, slice_index: int) -> dict:
    """Return simulated DICOM metadata for one slice without real DICOM files.

    DICOM metadata is how medical viewers know who the study belongs to, how
    pixels map to patient anatomy, and how grayscale intensity should be shown.
    This project still renders fake PNG slices, but the response teaches the
    metadata shape engineers see when integrating pydicom or WADO-RS later.
    """

    scan = get_scan_or_404(db, scan_id)
    if slice_index < 0 or slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")

    # PatientID is anonymized because production systems must protect PHI.
    # StudyDate lets clinicians and ML teams distinguish longitudinal studies.
    # Modality tells the viewer whether CT, MRI, PET, etc. rules should apply.
    # SliceThickness is the physical spacing through the patient in millimeters.
    # PixelSpacing maps each image pixel to real-world millimeters in-plane.
    # WindowCenter and WindowLevel control brightness/contrast for grayscale data.
    # ImageOrientationPatient describes how image rows/columns sit in 3D space.
    return {
        "scan_id": scan.id,
        "slice_index": slice_index,
        "PatientID": "ANON-001",
        "StudyDate": scan.created_at.strftime("%Y%m%d") if scan.created_at else "20240101",
        "Modality": scan.modality,
        "SliceThickness": 1.5,
        "PixelSpacing": [0.5, 0.5],
        "WindowCenter": 40 if scan.modality == "CT" else 600,
        "WindowLevel": 80 if scan.modality == "CT" else 1200,
        "ImageOrientationPatient": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
    }


def get_scan_metadata(scan: Scan) -> dict:
    """Return parsed scan metadata safe for product UI display."""

    return {
        "scan_id": scan.id,
        "scan_name": scan.name,
        "modality": scan.modality,
        "source_format": scan.source_format,
        "ingestion_status": scan.ingestion_status,
        "ingestion_error": scan.ingestion_error,
        "num_slices": scan.num_slices,
        "width": scan.width,
        "height": scan.height,
        "depth": scan.depth,
        "spacing": scan.spacing,
        "window_center": scan.window_center,
        "window_width": scan.window_width,
        "metadata": scan.imaging_metadata,
    }


def export_scan_annotations(db: Session, scan_id: UUID) -> dict:
    """Return a scan-level export containing only approved annotations.

    ML teams should train on labels that passed review. Pending annotations stay
    visible in counts so project managers know how much QA work remains, while
    rejected annotations are excluded from the payload because they represent
    labels the team decided should not influence model training.
    """

    scan = get_scan_or_404(db, scan_id)
    annotations = list(db.scalars(select(Annotation).where(Annotation.scan_id == scan_id).order_by(Annotation.slice_index, Annotation.created_at)))
    approved_annotations = [annotation for annotation in annotations if annotation.review_status == "approved"]
    status_counts = Counter(annotation.review_status for annotation in annotations)

    return {
        "scan_id": scan.id,
        "scan_name": scan.name,
        "modality": scan.modality,
        "num_slices": scan.num_slices,
        "export_timestamp": datetime.now(timezone.utc),
        "annotations": [
            {
                "id": annotation.id,
                "label": annotation.label,
                "annotation_type": annotation.annotation_type,
                "coordinates": annotation.coordinates,
                "slice_index": annotation.slice_index,
                "confidence_score": annotation.confidence_score,
                "created_by": annotation.created_by,
                "review_status": annotation.review_status,
            }
            for annotation in approved_annotations
        ],
        "total_annotations": len(annotations),
        "approved_count": status_counts.get("approved", 0),
        "pending_count": status_counts.get("pending", 0),
    }


def get_scan_annotation_stats(db: Session, scan_id: UUID) -> dict:
    """Return annotation distribution metrics for one scan.

    ML teams use these counts to spot class imbalance and missing slices before
    training. Project managers use the same numbers to estimate labeling and QA
    progress across radiologists, labels, geometry types, and review states.
    """

    get_scan_or_404(db, scan_id)
    annotations = list(db.scalars(select(Annotation).where(Annotation.scan_id == scan_id)))
    return {
        "total_annotations": len(annotations),
        "annotations_by_label": dict(Counter(annotation.label for annotation in annotations)),
        "annotations_by_type": dict(Counter(annotation.annotation_type for annotation in annotations)),
        "annotations_by_status": {
            status_name: Counter(annotation.review_status for annotation in annotations).get(status_name, 0)
            for status_name in ("pending", "approved", "rejected")
        },
        "slices_with_annotations": sorted({annotation.slice_index for annotation in annotations}),
        "radiologists_involved": sorted({annotation.created_by for annotation in annotations}),
    }
