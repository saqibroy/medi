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
from uuid import UUID

from fastapi import HTTPException, status
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, Scan
from ..schemas import ScanCreate


STORAGE_ROOT = Path(__file__).resolve().parents[1] / "data" / "sample_scan"


def list_scans(db: Session) -> list[Scan]:
    """Return all scans ordered by creation time for the left navigation panel."""

    return list(db.scalars(select(Scan).order_by(Scan.created_at.desc())))


def get_scan_or_404(db: Session, scan_id: UUID) -> Scan:
    """Fetch one scan or raise an HTTP 404 that FastAPI turns into JSON."""

    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan


def create_scan(db: Session, payload: ScanCreate) -> Scan:
    """Create fake scan metadata and a placeholder local file."""

    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = payload.file_name.replace("/", "_")
    file_path = STORAGE_ROOT / safe_name
    file_path.write_text("fake volumetric scan data for interview learning\n")

    scan = Scan(
        name=payload.name,
        file_path=str(file_path),
        modality=payload.modality,
        num_slices=payload.num_slices,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def get_slice_image_base64(db: Session, scan_id: UUID, slice_index: int) -> str:
    """Generate a PNG slice as base64 so React can render it without DICOM setup."""

    scan = get_scan_or_404(db, scan_id)
    if slice_index < 0 or slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")

    image = Image.new("L", (512, 512), color=18)
    draw = ImageDraw.Draw(image)
    # The ellipse shifts with slice_index to mimic a changing anatomical volume.
    offset = int((slice_index / max(scan.num_slices - 1, 1)) * 120)
    draw.ellipse((120 + offset, 100, 390 - offset // 2, 410), fill=95)
    draw.ellipse((210, 190 + offset // 3, 315, 295 + offset // 3), fill=160)
    draw.text((20, 20), f"{scan.modality} slice {slice_index}", fill=230)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


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
