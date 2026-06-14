"""Phase 2 imaging ingestion helpers."""

import gzip
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image


SourceFormat = Literal["synthetic", "nifti", "dicom", "dicom_zip", "unknown"]


class ImagingIngestionError(ValueError):
    """Raised when an uploaded imaging file cannot be parsed safely."""


@dataclass(frozen=True)
class NiftiVolume:
    """Parsed NIfTI geometry and voxel payload."""

    width: int
    height: int
    depth: int
    spacing: tuple[float, float, float]
    voxels: tuple[float, ...]


def detect_source_format(filename: str, content: bytes) -> SourceFormat:
    """Infer the uploaded imaging container from filename and file signature."""

    lower_name = filename.lower()
    if lower_name.endswith((".nii", ".nii.gz")):
        return "nifti"
    if lower_name.endswith(".zip") or content.startswith(b"PK\x03\x04"):
        return "dicom_zip"
    if lower_name.endswith(".dcm") or content[128:132] == b"DICM":
        return "dicom"
    return "unknown"


def build_initial_scan_profile(source_format: SourceFormat, modality: str, num_slices: int, storage_key: str) -> dict:
    """Return placeholder geometry and parser metadata for a new scan.

    The dimensions match the current generated preview slices. Real parser
    implementations will replace these values with file-derived geometry.
    """

    return {
        "storage_key": storage_key,
        "source_format": source_format,
        "ingestion_status": "ready",
        "ingestion_error": None,
        "imaging_metadata": {
            "source_format": source_format,
            "modality": modality,
            "parser_status": "not_parsed",
            "parser_note": "Phase 2 parser interface created; generated previews are still used.",
        },
        "width": 512,
        "height": 512,
        "depth": num_slices,
        "spacing": [1.0, 1.0, 1.0],
        "window_center": 40.0 if modality == "CT" else 600.0,
        "window_width": 80.0 if modality == "CT" else 1200.0,
    }


def parse_nifti_volume(filename: str, content: bytes) -> NiftiVolume:
    """Parse a small 3D float32 NIfTI-1 volume.

    The first production implementation intentionally supports the format used
    by our synthetic fixture: little-endian NIfTI-1, single-file `.nii` or
    `.nii.gz`, 3D, float32 voxels. More datatypes can be added behind this
    interface without changing upload code.
    """

    try:
        payload = gzip.decompress(content) if filename.lower().endswith(".gz") or content.startswith(b"\x1f\x8b") else content
    except OSError as error:
        raise ImagingIngestionError("NIfTI gzip payload could not be decompressed") from error
    if len(payload) < 352:
        raise ImagingIngestionError("NIfTI payload is too small")
    if struct.unpack_from("<i", payload, 0)[0] != 348:
        raise ImagingIngestionError("Unsupported NIfTI header size")
    if payload[344:348] not in (b"n+1\0", b"ni1\0"):
        raise ImagingIngestionError("Unsupported NIfTI magic")

    dim = struct.unpack_from("<8h", payload, 40)
    dimensions = dim[0]
    width, height, depth = dim[1], dim[2], dim[3]
    if dimensions < 3 or width < 1 or height < 1 or depth < 1:
        raise ImagingIngestionError("NIfTI volume must be a positive 3D image")

    datatype = struct.unpack_from("<h", payload, 70)[0]
    bitpix = struct.unpack_from("<h", payload, 72)[0]
    if datatype != 16 or bitpix != 32:
        raise ImagingIngestionError("Only float32 NIfTI volumes are supported")

    pixdim = struct.unpack_from("<8f", payload, 76)
    spacing = (float(pixdim[1] or 1.0), float(pixdim[2] or 1.0), float(pixdim[3] or 1.0))
    vox_offset = int(struct.unpack_from("<f", payload, 108)[0])
    voxel_count = width * height * depth
    expected_bytes = voxel_count * 4
    if vox_offset < 348 or len(payload) < vox_offset + expected_bytes:
        raise ImagingIngestionError("NIfTI voxel payload is incomplete")

    voxels = struct.unpack_from(f"<{voxel_count}f", payload, vox_offset)
    return NiftiVolume(width=width, height=height, depth=depth, spacing=spacing, voxels=voxels)


def write_nifti_preview_slices(volume: NiftiVolume, preview_root: Path) -> None:
    """Write one normalized 8-bit PNG per NIfTI slice."""

    preview_root.mkdir(parents=True, exist_ok=True)
    slice_size = volume.width * volume.height
    for slice_index in range(volume.depth):
        start = slice_index * slice_size
        slice_values = volume.voxels[start : start + slice_size]
        minimum = min(slice_values)
        maximum = max(slice_values)
        value_range = maximum - minimum
        if value_range == 0:
            pixels = [0 for _ in slice_values]
        else:
            pixels = [max(0, min(255, round(((value - minimum) / value_range) * 255))) for value in slice_values]
        image = Image.new("L", (volume.width, volume.height))
        image.putdata(pixels)
        image.save(preview_root / f"{slice_index:06d}.png", format="PNG")


def build_nifti_scan_profile(filename: str, content: bytes, modality: str, storage_key: str, preview_root: Path) -> dict:
    """Parse NIfTI content, generate preview slices, and return scan fields."""

    volume = parse_nifti_volume(filename, content)
    write_nifti_preview_slices(volume, preview_root)
    return {
        "storage_key": storage_key,
        "source_format": "nifti",
        "ingestion_status": "ready",
        "ingestion_error": None,
        "imaging_metadata": {
            "source_format": "nifti",
            "modality": modality,
            "parser_status": "parsed",
            "datatype": "float32",
            "preview_slice_count": volume.depth,
        },
        "width": volume.width,
        "height": volume.height,
        "depth": volume.depth,
        "spacing": list(volume.spacing),
        "window_center": 40.0 if modality == "CT" else 600.0,
        "window_width": 80.0 if modality == "CT" else 1200.0,
    }
