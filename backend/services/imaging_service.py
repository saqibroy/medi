"""Phase 2 imaging ingestion helpers."""

import gzip
import struct
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image


SourceFormat = Literal["synthetic", "nifti", "dicom", "dicom_zip", "unknown"]
DEIDENTIFICATION_PROFILE_VERSION = "medi-deid-screening-v1"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 1024 * 1024
MAX_SERIES_SLICES = 256
MAX_SERIES_PIXELS = MAX_IMAGE_PIXELS * MAX_SERIES_SLICES
MAX_ZIP_COMPRESSION_RATIO = 100
ALLOWED_UPLOAD_EXTENSIONS = (".nii", ".nii.gz", ".dcm", ".zip")
ALLOWED_UPLOAD_MIME_TYPES = {
    "",
    "application/octet-stream",
    "application/dicom",
    "application/gzip",
    "application/x-gzip",
    "application/zip",
    "application/x-zip-compressed",
}
DICOM_PHI_TAGS = {
    (0x0008, 0x0050): "AccessionNumber",
    (0x0008, 0x0080): "InstitutionName",
    (0x0008, 0x0090): "ReferringPhysicianName",
    (0x0010, 0x0010): "PatientName",
    (0x0010, 0x0020): "PatientID",
    (0x0010, 0x0030): "PatientBirthDate",
    (0x0010, 0x0040): "PatientSex",
}


class ImagingIngestionError(ValueError):
    """Raised when an uploaded imaging file cannot be parsed safely."""


def validate_upload_size(content: bytes) -> None:
    """Reject uploads that are too large for synchronous Phase 2 parsing."""

    if len(content) > MAX_UPLOAD_BYTES:
        raise ImagingIngestionError("Uploaded scan exceeds the Phase 2 upload size limit")


def validate_upload_hint(filename: str, content_type: str | None) -> None:
    """Reject uploads that do not look like supported Phase 2 imaging files."""

    lower_name = filename.lower()
    if not lower_name.endswith(ALLOWED_UPLOAD_EXTENSIONS):
        raise ImagingIngestionError("Unsupported scan file type. Upload .nii, .nii.gz, .dcm, or .zip files.")
    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise ImagingIngestionError("Unsupported scan MIME type for Phase 2 upload")


@dataclass(frozen=True)
class NiftiVolume:
    """Parsed NIfTI geometry and voxel payload."""

    width: int
    height: int
    depth: int
    spacing: tuple[float, float, float]
    voxels: tuple[float, ...]
    risk_flags: tuple[str, ...]


@dataclass(frozen=True)
class DicomImage:
    """Parsed single-frame DICOM geometry and pixels."""

    width: int
    height: int
    spacing: tuple[float, float, float]
    pixels: tuple[int, ...]
    modality: str
    window_center: float | None
    window_width: float | None
    phi_warnings: tuple[str, ...]
    private_tag_detected: bool
    burned_in_annotation: str
    archive_member_name_risk: bool = False


def deidentification_fields(status_name: str, risk_flags: tuple[str, ...] = ()) -> dict:
    """Build a versioned decision record containing no detected PHI values."""

    return {
        "deidentification_status": status_name,
        "deidentification_profile_version": DEIDENTIFICATION_PROFILE_VERSION,
        "deidentification_checked_at": datetime.now(timezone.utc),
        "deidentification_evidence": {
            "profile_version": DEIDENTIFICATION_PROFILE_VERSION,
            "tool": "medi-built-in-screening",
            "tool_version": DEIDENTIFICATION_PROFILE_VERSION,
            "decision": status_name,
            "risk_flags": list(dict.fromkeys(risk_flags)),
        },
    }


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
        **deidentification_fields("synthetic"),
        "storage_key": storage_key,
        "source_format": source_format,
        "ingestion_status": "ready",
        "ingestion_error": None,
        "imaging_metadata": {
            "source_format": source_format,
            "modality": modality,
            "parser_status": "not_parsed",
            "data_safety": "synthetic",
            "deidentification_status": "synthetic_no_phi",
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

    risk_flags = []
    for field_name, start, end in (
        ("NiftiDescription", 148, 228),
        ("NiftiAuxFile", 228, 252),
        ("NiftiIntentName", 328, 344),
    ):
        if payload[start:end].decode("utf-8", errors="ignore").strip("\0 "):
            risk_flags.append(field_name)

    dim = struct.unpack_from("<8h", payload, 40)
    dimensions = dim[0]
    width, height, depth = dim[1], dim[2], dim[3]
    if dimensions < 3 or width < 1 or height < 1 or depth < 1:
        raise ImagingIngestionError("NIfTI volume must be a positive 3D image")
    if width * height > MAX_IMAGE_PIXELS or width * height * depth > MAX_SERIES_PIXELS:
        raise ImagingIngestionError("NIfTI volume exceeds Phase 2 preview limits")

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
    return NiftiVolume(width=width, height=height, depth=depth, spacing=spacing, voxels=voxels, risk_flags=tuple(risk_flags))


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


def _normalize_to_png(values: tuple[float, ...] | tuple[int, ...], width: int, height: int, path: Path) -> None:
    """Normalize numeric pixels to one 8-bit PNG."""

    minimum = min(values)
    maximum = max(values)
    value_range = maximum - minimum
    if value_range == 0:
        pixels = [0 for _ in values]
    else:
        pixels = [max(0, min(255, round(((value - minimum) / value_range) * 255))) for value in values]
    image = Image.new("L", (width, height))
    image.putdata(pixels)
    image.save(path, format="PNG")


def build_nifti_scan_profile(filename: str, content: bytes, modality: str, storage_key: str, preview_root: Path) -> dict:
    """Parse NIfTI content, generate preview slices, and return scan fields."""

    volume = parse_nifti_volume(filename, content)
    write_nifti_preview_slices(volume, preview_root)
    decision = "quarantined" if volume.risk_flags else "passed"
    return {
        **deidentification_fields(decision, volume.risk_flags),
        "storage_key": storage_key,
        "source_format": "nifti",
        "ingestion_status": "quarantined" if volume.risk_flags else "ready",
        "ingestion_error": "Upload quarantined by medical-image intake policy" if volume.risk_flags else None,
        "imaging_metadata": {
            "source_format": "nifti",
            "modality": modality,
            "parser_status": "parsed",
            "data_safety": "uploaded",
            "deidentification_status": decision,
            "deidentification_profile_version": DEIDENTIFICATION_PROFILE_VERSION,
            "risk_flags": list(volume.risk_flags),
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


def _parse_dicom_number(value: bytes) -> float | None:
    text = value.decode("ascii", errors="ignore").strip().strip("\0")
    if not text:
        return None
    return float(text.split("\\")[0])


def _parse_dicom_spacing(value: bytes) -> tuple[float, float]:
    parts = value.decode("ascii", errors="ignore").strip().split("\\")
    if len(parts) < 2:
        return (1.0, 1.0)
    return (float(parts[0]), float(parts[1]))


def _parse_dicom_text(value: bytes) -> str:
    return value.decode("ascii", errors="ignore").strip().strip("\0")


def parse_dicom_image(content: bytes) -> DicomImage:
    """Parse a tiny Explicit VR Little Endian single-frame DICOM image."""

    if len(content) < 132 or content[128:132] != b"DICM":
        raise ImagingIngestionError("DICOM file is missing the DICM preamble")

    offset = 132
    rows: int | None = None
    columns: int | None = None
    bits_allocated: int | None = None
    pixel_representation = 0
    pixel_spacing = (1.0, 1.0)
    slice_thickness = 1.0
    modality = "unknown"
    window_center: float | None = None
    window_width: float | None = None
    pixel_data: bytes | None = None
    phi_warnings: list[str] = []
    private_tag_detected = False
    burned_in_annotation = "missing"
    long_vrs = {b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN"}

    while offset + 8 <= len(content):
        group, element = struct.unpack_from("<HH", content, offset)
        vr = content[offset + 4 : offset + 6]
        offset += 6
        if vr in long_vrs:
            if offset + 6 > len(content):
                break
            offset += 2
            length = struct.unpack_from("<I", content, offset)[0]
            offset += 4
        else:
            length = struct.unpack_from("<H", content, offset)[0]
            offset += 2
        value = content[offset : offset + length]
        offset += length

        tag = (group, element)
        if tag in DICOM_PHI_TAGS and _parse_dicom_text(value):
            phi_warnings.append(DICOM_PHI_TAGS[tag])
        if group % 2 == 1 and value.strip(b"\0 "):
            private_tag_detected = True
        if tag == (0x0008, 0x0060):
            modality = _parse_dicom_text(value)
        elif tag == (0x0018, 0x0050):
            slice_thickness = _parse_dicom_number(value) or 1.0
        elif tag == (0x0028, 0x0010):
            rows = struct.unpack_from("<H", value, 0)[0]
        elif tag == (0x0028, 0x0011):
            columns = struct.unpack_from("<H", value, 0)[0]
        elif tag == (0x0028, 0x0030):
            pixel_spacing = _parse_dicom_spacing(value)
        elif tag == (0x0028, 0x0100):
            bits_allocated = struct.unpack_from("<H", value, 0)[0]
        elif tag == (0x0028, 0x0103):
            pixel_representation = struct.unpack_from("<H", value, 0)[0]
        elif tag == (0x0028, 0x0301):
            burned_in_annotation = _parse_dicom_text(value).upper() or "missing"
        elif tag == (0x0028, 0x1050):
            window_center = _parse_dicom_number(value)
        elif tag == (0x0028, 0x1051):
            window_width = _parse_dicom_number(value)
        elif tag == (0x7FE0, 0x0010):
            pixel_data = value

    if rows is None or columns is None or bits_allocated is None or pixel_data is None:
        raise ImagingIngestionError("DICOM image is missing required pixel metadata")
    if rows * columns > MAX_IMAGE_PIXELS:
        raise ImagingIngestionError("DICOM image exceeds Phase 2 preview limits")
    if bits_allocated != 16 or pixel_representation != 0:
        raise ImagingIngestionError("Only unsigned 16-bit DICOM pixels are supported")

    pixel_count = rows * columns
    expected_bytes = pixel_count * 2
    if len(pixel_data) < expected_bytes:
        raise ImagingIngestionError("DICOM pixel payload is incomplete")
    pixels = struct.unpack_from(f"<{pixel_count}H", pixel_data, 0)
    return DicomImage(
        width=columns,
        height=rows,
        spacing=(pixel_spacing[0], pixel_spacing[1], slice_thickness),
        pixels=pixels,
        modality=modality,
        window_center=window_center,
        window_width=window_width,
        phi_warnings=tuple(dict.fromkeys(phi_warnings)),
        private_tag_detected=private_tag_detected,
        burned_in_annotation=burned_in_annotation,
    )


def _dicom_risk_flags(images: list[DicomImage]) -> tuple[str, ...]:
    flags = [warning for image in images for warning in image.phi_warnings]
    if any(image.private_tag_detected for image in images):
        flags.append("PrivateDataElement")
    if any(image.archive_member_name_risk for image in images):
        flags.append("ArchiveMemberName")
    burned_in_values = {image.burned_in_annotation for image in images}
    if burned_in_values != {"NO"}:
        flags.append("BurnedInAnnotationYes" if "YES" in burned_in_values else "BurnedInAnnotationUnknown")
    return tuple(dict.fromkeys(sorted(flags)))


def build_dicom_scan_profile(content: bytes, modality: str, storage_key: str, preview_root: Path) -> dict:
    """Parse a single DICOM file, generate a preview slice, and return scan fields."""

    image = parse_dicom_image(content)
    preview_root.mkdir(parents=True, exist_ok=True)
    _normalize_to_png(image.pixels, image.width, image.height, preview_root / "000000.png")
    risk_flags = _dicom_risk_flags([image])
    decision = "quarantined" if risk_flags else "passed"
    return {
        **deidentification_fields(decision, risk_flags),
        "storage_key": storage_key,
        "source_format": "dicom",
        "ingestion_status": "quarantined" if risk_flags else "ready",
        "ingestion_error": "Upload quarantined by medical-image intake policy" if risk_flags else None,
        "imaging_metadata": {
            "source_format": "dicom",
            "modality": image.modality or modality,
            "parser_status": "parsed",
            "data_safety": "uploaded",
            "deidentification_status": decision,
            "deidentification_profile_version": DEIDENTIFICATION_PROFILE_VERSION,
            "datatype": "uint16",
            "preview_slice_count": 1,
            "phi_warnings": list(image.phi_warnings),
            "risk_flags": list(risk_flags),
            "private_tag_detected": image.private_tag_detected,
            "burned_in_annotation": image.burned_in_annotation,
        },
        "width": image.width,
        "height": image.height,
        "depth": 1,
        "spacing": list(image.spacing),
        "window_center": image.window_center if image.window_center is not None else (40.0 if modality == "CT" else 600.0),
        "window_width": image.window_width if image.window_width is not None else (80.0 if modality == "CT" else 1200.0),
    }


def parse_dicom_zip(content: bytes) -> list[DicomImage]:
    """Parse a zipped single-series DICOM upload."""

    images: list[DicomImage] = []
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > MAX_SERIES_SLICES:
                raise ImagingIngestionError("DICOM zip contains too many files for Phase 2 ingestion")
            for member in sorted(members, key=lambda item: item.filename):
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ImagingIngestionError("DICOM zip contains an unsafe path")
                if member.compress_size and member.file_size / member.compress_size > MAX_ZIP_COMPRESSION_RATIO:
                    raise ImagingIngestionError("DICOM zip compression ratio is too high")
                if not member.filename.lower().endswith(".dcm"):
                    continue
                image = parse_dicom_image(archive.read(member))
                basename = member_path.name.lower()
                stem = basename.removesuffix(".dcm")
                safe_stem = stem.isdigit() or (stem.startswith("im") and stem[2:].isdigit()) or (
                    stem.startswith(("slice-", "slice_")) and stem[6:].isdigit()
                )
                safe_directories = all(part.lower() in {"series", "dicom"} for part in member_path.parts[:-1])
                if not safe_stem or not safe_directories:
                    image = replace(image, archive_member_name_risk=True)
                images.append(image)
    except zipfile.BadZipFile as error:
        raise ImagingIngestionError("DICOM zip could not be opened") from error

    if not images:
        raise ImagingIngestionError("DICOM zip did not contain any .dcm files")

    first = images[0]
    for image in images[1:]:
        if image.width != first.width or image.height != first.height:
            raise ImagingIngestionError("DICOM zip contains inconsistent image dimensions")
    if first.width * first.height * len(images) > MAX_SERIES_PIXELS:
        raise ImagingIngestionError("DICOM zip exceeds Phase 2 preview limits")
    return images


def build_dicom_zip_scan_profile(content: bytes, modality: str, storage_key: str, preview_root: Path) -> dict:
    """Parse a zipped DICOM series, generate previews, and return scan fields."""

    images = parse_dicom_zip(content)
    preview_root.mkdir(parents=True, exist_ok=True)
    for index, image in enumerate(images):
        _normalize_to_png(image.pixels, image.width, image.height, preview_root / f"{index:06d}.png")

    first = images[0]
    phi_warnings = sorted({warning for image in images for warning in image.phi_warnings})
    risk_flags = _dicom_risk_flags(images)
    decision = "quarantined" if risk_flags else "passed"
    return {
        **deidentification_fields(decision, risk_flags),
        "storage_key": storage_key,
        "source_format": "dicom_zip",
        "ingestion_status": "quarantined" if risk_flags else "ready",
        "ingestion_error": "Upload quarantined by medical-image intake policy" if risk_flags else None,
        "imaging_metadata": {
            "source_format": "dicom_zip",
            "modality": first.modality or modality,
            "parser_status": "parsed",
            "data_safety": "uploaded",
            "deidentification_status": decision,
            "deidentification_profile_version": DEIDENTIFICATION_PROFILE_VERSION,
            "datatype": "uint16",
            "preview_slice_count": len(images),
            "phi_warnings": phi_warnings,
            "risk_flags": list(risk_flags),
            "private_tag_detected": any(image.private_tag_detected for image in images),
            "archive_member_name_risk": any(image.archive_member_name_risk for image in images),
            "burned_in_annotation": "NO" if all(image.burned_in_annotation == "NO" for image in images) else "unsafe_or_missing",
        },
        "width": first.width,
        "height": first.height,
        "depth": len(images),
        "spacing": [first.spacing[0], first.spacing[1], first.spacing[2]],
        "window_center": first.window_center if first.window_center is not None else (40.0 if modality == "CT" else 600.0),
        "window_width": first.window_width if first.window_width is not None else (80.0 if modality == "CT" else 1200.0),
    }
