"""Business logic for scan metadata and simulated image slices.

Routers should stay thin: they translate HTTP into service calls. This service
owns scan-specific decisions such as how local storage paths are created and how
fake slice images are generated for the learning viewer.
"""

import base64
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, Project, Scan, User
from ..schemas import ScanCreate
from ..settings import get_settings
from .imaging_service import ImagingIngestionError, SourceFormat, build_dicom_scan_profile, build_dicom_zip_scan_profile, build_initial_scan_profile, build_nifti_scan_profile, deidentification_fields, detect_source_format, validate_upload_hint, validate_upload_size
from .storage_service import PrivateStorage, get_private_storage, scan_prefix


STORAGE_ROOT = Path(__file__).resolve().parents[1] / "data" / "sample_scan"


def _storage() -> PrivateStorage:
    return get_private_storage(STORAGE_ROOT)


def _store_generated_previews(storage: PrivateStorage, preview_prefix: str, preview_root: Path) -> None:
    for preview_path in preview_root.glob("*.png"):
        storage.put_bytes(f"{preview_prefix}/{preview_path.name}", preview_path.read_bytes())


def _neutral_original_name(source_format: SourceFormat, original_filename: str) -> str:
    """Never retain a potentially identifying client filename in object storage."""

    if source_format == "dicom":
        return "original.dcm"
    if source_format == "dicom_zip":
        return "series.zip"
    if source_format == "nifti":
        return "original.nii.gz" if original_filename.lower().endswith(".gz") else "original.nii"
    return "original.bin"


def require_scan_ready(scan: Scan) -> Scan:
    """Deny pixels, annotations, masks, and exports until intake is approved."""

    if scan.ingestion_status == "quarantined":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scan is quarantined by the medical-image intake policy")
    if scan.ingestion_status in {"pending", "processing"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scan ingestion is not ready yet")
    if scan.ingestion_status == "failed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=scan.ingestion_error or "Scan ingestion failed")
    if scan.ingestion_status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scan is not available")
    return scan


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


def create_scan(db: Session, payload: ScanCreate, organization_id: UUID) -> Scan:
    """Create fake scan metadata and a placeholder local file."""

    scan_id = uuid4()
    prefix = scan_prefix(organization_id, payload.project_id or "unassigned", scan_id)
    original_key = f"{prefix}/original/synthetic-placeholder.bin"
    _storage().put_bytes(original_key, b"synthetic volumetric scan placeholder\n")
    scan_profile = build_initial_scan_profile("synthetic", payload.modality, payload.num_slices, prefix)

    scan = Scan(
        id=scan_id,
        name=payload.name,
        project_id=payload.project_id,
        file_path=original_key,
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
    return create_scan(db, payload, current_user.organization_id)


def _build_failed_scan_profile(source_format: str, modality: str, num_slices: int, storage_key: str, error: ImagingIngestionError) -> dict:
    """Return safe metadata for an upload that was stored but could not parse."""

    return {
        **deidentification_fields("not_evaluated"),
        "storage_key": storage_key,
        "source_format": source_format,
        "ingestion_status": "failed",
        "ingestion_error": str(error),
        "imaging_metadata": {
            "source_format": source_format,
            "modality": modality,
            "parser_status": "failed",
            "parser_error": str(error),
            "data_safety": "uploaded",
            "deidentification_status": "not_evaluated",
        },
        "width": None,
        "height": None,
        "depth": num_slices,
        "spacing": None,
        "window_center": 40.0 if modality == "CT" else 600.0,
        "window_width": 80.0 if modality == "CT" else 1200.0,
    }


def _build_uploaded_scan_profile(
    filename: str,
    content: bytes,
    modality: str,
    num_slices: int,
    scan_storage_root: Path,
    preview_storage_root: Path,
) -> dict:
    """Parse uploaded bytes into scan fields or return a failed profile."""

    source_format = detect_source_format(filename, content)
    try:
        if source_format == "nifti":
            return build_nifti_scan_profile(filename, content, modality, str(scan_storage_root), preview_storage_root)
        if source_format == "dicom":
            return build_dicom_scan_profile(content, modality, str(scan_storage_root), preview_storage_root)
        if source_format == "dicom_zip":
            return build_dicom_zip_scan_profile(content, modality, str(scan_storage_root), preview_storage_root)
        return build_initial_scan_profile(source_format, modality, num_slices, str(scan_storage_root))
    except ImagingIngestionError as error:
        return _build_failed_scan_profile(source_format, modality, num_slices, str(scan_storage_root), error)


def create_uploaded_scan_for_user(
    db: Session,
    project_id: UUID,
    name: str,
    modality: str,
    num_slices: int,
    original_filename: str,
    content_type: str | None,
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
    try:
        validate_upload_hint(original_filename, content_type)
        validate_upload_size(content)
    except ImagingIngestionError as error:
        status_code = status.HTTP_413_CONTENT_TOO_LARGE if "size limit" in str(error) else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        raise HTTPException(status_code=status_code, detail=str(error)) from error

    scan_id = uuid4()
    prefix = scan_prefix(project.organization_id, project_id, scan_id)
    source_format = detect_source_format(original_filename, content)
    neutral_original_name = _neutral_original_name(source_format, original_filename)
    quarantine_key = f"{prefix}/quarantine/original/{neutral_original_name}"
    approved_key = f"{prefix}/original/{neutral_original_name}"
    preview_prefix = f"{prefix}/derived/preview"
    storage = _storage()
    storage.put_bytes(quarantine_key, content)
    with TemporaryDirectory(prefix="medi-preview-") as temporary_directory:
        preview_root = Path(temporary_directory)
        scan_profile = _build_uploaded_scan_profile(
            neutral_original_name,
            content,
            modality,
            num_slices,
            Path(prefix),
            preview_root,
        )
        if scan_profile["ingestion_status"] == "ready":
            storage.put_bytes(approved_key, content)
            storage.delete(quarantine_key)
            _store_generated_previews(storage, preview_prefix, preview_root)
            stored_original_key = approved_key
        else:
            storage.delete_prefix(preview_prefix)
            stored_original_key = quarantine_key

    scan = Scan(
        id=scan_id,
        project_id=project_id,
        name=name,
        file_path=stored_original_key,
        modality=modality,
        num_slices=scan_profile["depth"] or num_slices,
        **scan_profile,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def reprocess_scan_for_user(db: Session, scan_id: UUID, current_user: User) -> Scan:
    """Retry parsing a failed uploaded scan from its stored original bytes."""

    scan = get_scan_for_user_or_404(db, scan_id, current_user)
    if scan.ingestion_status != "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only failed scans can be reprocessed")
    storage = _storage()
    if not storage.exists(scan.file_path) or not scan.storage_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Original scan file is unavailable for reprocessing")

    content = storage.get_bytes(scan.file_path)
    preview_prefix = f"{scan.storage_key}/derived/preview"
    storage.delete_prefix(preview_prefix)
    source_format = detect_source_format(PurePosixPath(scan.file_path).name, content)
    neutral_original_name = _neutral_original_name(source_format, PurePosixPath(scan.file_path).name)
    quarantine_key = f"{scan.storage_key}/quarantine/original/{neutral_original_name}"
    approved_key = f"{scan.storage_key}/original/{neutral_original_name}"
    with TemporaryDirectory(prefix="medi-preview-") as temporary_directory:
        preview_root = Path(temporary_directory)
        scan_profile = _build_uploaded_scan_profile(
            neutral_original_name,
            content,
            scan.modality,
            scan.num_slices,
            Path(scan.storage_key),
            preview_root,
        )
        if scan_profile["ingestion_status"] == "ready":
            storage.put_bytes(approved_key, content)
            _store_generated_previews(storage, preview_prefix, preview_root)
            stored_original_key = approved_key
        else:
            storage.put_bytes(quarantine_key, content)
            stored_original_key = quarantine_key
    if scan.file_path != stored_original_key:
        storage.delete(scan.file_path)
    scan.file_path = stored_original_key
    for field_name, value in scan_profile.items():
        setattr(scan, field_name, value)
    scan.num_slices = scan_profile["depth"] or scan.num_slices
    db.commit()
    db.refresh(scan)
    return scan


def _read_derived_preview_base64(scan: Scan, slice_index: int) -> str | None:
    """Return a derived preview PNG if ingestion generated one."""

    if not scan.storage_key:
        return None
    preview_key = f"{scan.storage_key}/derived/preview/{slice_index:06d}.png"
    storage = _storage()
    if not storage.exists(preview_key):
        return None
    return base64.b64encode(storage.get_bytes(preview_key)).decode("ascii")


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

    require_scan_ready(scan)
    if slice_index < 0 or slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    return _read_derived_preview_base64(scan, slice_index) or _generate_placeholder_slice_base64(scan, slice_index)


def get_slice_image_base64(db: Session, scan_id: UUID, slice_index: int) -> str:
    """Return a PNG slice as base64 so React can render it."""

    return _get_slice_image_base64(get_scan_or_404(db, scan_id), slice_index)


def get_slice_image_base64_for_user(db: Session, scan_id: UUID, slice_index: int, current_user: User) -> str:
    """Return a slice after checking scan access."""

    return _get_slice_image_base64(get_scan_for_user_or_404(db, scan_id, current_user), slice_index)


def get_slice_signed_url_for_user(db: Session, scan_id: UUID, slice_index: int, current_user: User) -> dict:
    """Authorize one derived preview and return a short-lived S3 GET URL."""

    scan = get_scan_for_user_or_404(db, scan_id, current_user)
    require_scan_ready(scan)
    if slice_index < 0 or slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")
    if not scan.storage_key or not scan.storage_key.startswith(f"org/{current_user.organization_id}/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")
    preview_key = f"{scan.storage_key}/derived/preview/{slice_index:06d}.png"
    storage = _storage()
    if not storage.exists(preview_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")
    settings = get_settings()
    if settings.scan_storage_backend != "s3":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Signed preview URLs require S3 storage")
    return {
        "scan_id": scan.id,
        "slice_index": slice_index,
        "url": storage.signed_get_url(preview_key, settings.scan_storage_signed_url_ttl_seconds),
        "expires_in_seconds": settings.scan_storage_signed_url_ttl_seconds,
    }


def get_slice_dicom_metadata(db: Session, scan_id: UUID, slice_index: int) -> dict:
    """Return simulated DICOM metadata for one slice without real DICOM files.

    DICOM metadata is how medical viewers know who the study belongs to, how
    pixels map to patient anatomy, and how grayscale intensity should be shown.
    This project still renders fake PNG slices, but the response teaches the
    metadata shape engineers see when integrating pydicom or WADO-RS later.
    """

    scan = require_scan_ready(get_scan_or_404(db, scan_id))
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
        "deidentification_status": scan.deidentification_status,
        "deidentification_profile_version": scan.deidentification_profile_version,
        "deidentification_checked_at": scan.deidentification_checked_at,
        "deidentification_evidence": scan.deidentification_evidence,
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

    scan = require_scan_ready(get_scan_or_404(db, scan_id))
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
                "assigned_to_user_id": annotation.assigned_to_user_id,
                "review_status": annotation.review_status,
            }
            for annotation in approved_annotations
        ],
        "total_annotations": len(annotations),
        "approved_count": status_counts.get("approved", 0),
        "pending_count": status_counts.get("pending", 0),
    }


def export_scan_coco(db: Session, scan_id: UUID) -> dict:
    """Return approved scan bounding boxes in COCO format."""

    scan = require_scan_ready(get_scan_or_404(db, scan_id))
    from .export_service import build_coco_export

    return build_coco_export(db, [scan], project_id=scan.project_id, scan_id=scan.id)


def export_scan_csv(db: Session, scan_id: UUID) -> dict:
    """Return scan annotations as spreadsheet-friendly CSV."""

    scan = require_scan_ready(get_scan_or_404(db, scan_id))
    from .export_service import build_csv_export

    return build_csv_export(db, [scan], project_id=scan.project_id, scan_id=scan.id)


def export_scan_yolo(db: Session, scan_id: UUID) -> dict:
    """Return approved scan bounding boxes in YOLO format."""

    scan = require_scan_ready(get_scan_or_404(db, scan_id))
    from .export_service import build_yolo_export

    return build_yolo_export(db, [scan], project_id=scan.project_id, scan_id=scan.id)


def export_scan_segmentation(db: Session, scan_id: UUID) -> dict:
    """Return approved scan segmentations as a mask manifest."""

    scan = require_scan_ready(get_scan_or_404(db, scan_id))
    from .export_service import build_segmentation_export

    return build_segmentation_export(db, [scan], project_id=scan.project_id, scan_id=scan.id)


def get_scan_annotation_stats(db: Session, scan_id: UUID) -> dict:
    """Return annotation distribution metrics for one scan.

    ML teams use these counts to spot class imbalance and missing slices before
    training. Project managers use the same numbers to estimate labeling and QA
    progress across radiologists, labels, geometry types, and review states.
    """

    require_scan_ready(get_scan_or_404(db, scan_id))
    annotations = list(db.scalars(select(Annotation).where(Annotation.scan_id == scan_id)))
    status_counts = Counter(annotation.review_status for annotation in annotations)
    reviewed_count = status_counts.get("approved", 0) + status_counts.get("rejected", 0) + status_counts.get("needs_changes", 0)
    return {
        "total_annotations": len(annotations),
        "approved_count": status_counts.get("approved", 0),
        "pending_count": status_counts.get("pending", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "needs_changes_count": status_counts.get("needs_changes", 0),
        "review_completion_rate": reviewed_count / len(annotations) if annotations else 0,
        "annotations_by_label": dict(Counter(annotation.label for annotation in annotations)),
        "annotations_by_type": dict(Counter(annotation.annotation_type for annotation in annotations)),
        "annotations_by_status": {
            status_name: status_counts.get(status_name, 0)
            for status_name in ("pending", "approved", "rejected", "needs_changes")
        },
        "slices_with_annotations": sorted({annotation.slice_index for annotation in annotations}),
        "radiologists_involved": sorted({annotation.created_by for annotation in annotations}),
    }
