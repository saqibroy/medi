"""Business logic for scan metadata and simulated image slices.

Routers should stay thin: they translate HTTP into service calls. This service
owns scan-specific decisions such as how local storage paths are created and how
fake slice images are generated for the learning viewer.
"""

import base64
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Scan
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
