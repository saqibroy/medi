"""Synthetic imaging fixtures for parser and ingestion tests."""

from __future__ import annotations

import gzip
import struct
import zipfile
from pathlib import Path


def write_synthetic_nifti(
    path: Path,
    *,
    width: int = 8,
    height: int = 6,
    depth: int = 4,
    spacing: tuple[float, float, float] = (0.7, 0.7, 1.5),
) -> Path:
    """Write a tiny NIfTI-1 `.nii.gz` volume for deterministic parser tests.

    The fixture uses little-endian float32 voxels and stores data as a simple
    ramp so parser tests can verify dimensions, spacing, and payload length
    without needing a real patient scan.
    """

    if width < 1 or height < 1 or depth < 1:
        raise ValueError("Synthetic NIfTI dimensions must be positive")

    header = bytearray(348)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, 3, width, height, depth, 1, 1, 1, 1)
    struct.pack_into("<h", header, 70, 16)  # DT_FLOAT32
    struct.pack_into("<h", header, 72, 32)
    struct.pack_into("<8f", header, 76, 0.0, spacing[0], spacing[1], spacing[2], 0.0, 0.0, 0.0, 0.0)
    struct.pack_into("<f", header, 108, 352.0)
    header[344:348] = b"n+1\0"

    voxel_count = width * height * depth
    voxels = struct.pack(f"<{voxel_count}f", *(float(index) for index in range(voxel_count)))
    payload = bytes(header) + b"\0\0\0\0" + voxels

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as output:
        output.write(payload)
    return path


def _dicom_element(tag_group: int, tag_element: int, vr: bytes, value: bytes) -> bytes:
    """Build one Explicit VR Little Endian DICOM data element."""

    if len(value) % 2:
        value += b" "
    header = struct.pack("<HH2s", tag_group, tag_element, vr)
    if vr in {b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN"}:
        return header + b"\0\0" + struct.pack("<I", len(value)) + value
    return header + struct.pack("<H", len(value)) + value


def write_synthetic_dicom(
    path: Path,
    *,
    width: int = 7,
    height: int = 5,
    spacing: tuple[float, float] = (0.8, 0.8),
    slice_thickness: float = 1.5,
    patient_name: str | None = None,
    patient_id: str | None = None,
    accession_number: str | None = None,
) -> Path:
    """Write a tiny Explicit VR Little Endian DICOM file for parser tests."""

    if width < 1 or height < 1:
        raise ValueError("Synthetic DICOM dimensions must be positive")

    pixel_count = width * height
    pixels = struct.pack(f"<{pixel_count}H", *(index * 16 for index in range(pixel_count)))
    payload = bytearray(b"\0" * 128 + b"DICM")
    if accession_number:
        payload += _dicom_element(0x0008, 0x0050, b"SH", accession_number.encode("ascii"))
    payload += _dicom_element(0x0008, 0x0060, b"CS", b"CT")
    if patient_name:
        payload += _dicom_element(0x0010, 0x0010, b"PN", patient_name.encode("ascii"))
    if patient_id:
        payload += _dicom_element(0x0010, 0x0020, b"LO", patient_id.encode("ascii"))
    payload += _dicom_element(0x0018, 0x0050, b"DS", str(slice_thickness).encode("ascii"))
    payload += _dicom_element(0x0028, 0x0010, b"US", struct.pack("<H", height))
    payload += _dicom_element(0x0028, 0x0011, b"US", struct.pack("<H", width))
    payload += _dicom_element(0x0028, 0x0030, b"DS", f"{spacing[0]}\\{spacing[1]}".encode("ascii"))
    payload += _dicom_element(0x0028, 0x0100, b"US", struct.pack("<H", 16))
    payload += _dicom_element(0x0028, 0x0101, b"US", struct.pack("<H", 16))
    payload += _dicom_element(0x0028, 0x0103, b"US", struct.pack("<H", 0))
    payload += _dicom_element(0x0028, 0x1050, b"DS", b"40")
    payload += _dicom_element(0x0028, 0x1051, b"DS", b"400")
    payload += _dicom_element(0x7FE0, 0x0010, b"OW", pixels)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(payload))
    return path


def write_synthetic_dicom_zip(
    path: Path,
    *,
    width: int = 7,
    height: int = 5,
    depth: int = 3,
    spacing: tuple[float, float] = (0.8, 0.8),
    slice_thickness: float = 1.5,
) -> Path:
    """Write a zip file containing a tiny synthetic DICOM series."""

    if depth < 1:
        raise ValueError("Synthetic DICOM series depth must be positive")

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index in range(depth):
            slice_path = path.parent / f"slice-{index:06d}.dcm"
            write_synthetic_dicom(slice_path, width=width, height=height, spacing=spacing, slice_thickness=slice_thickness)
            archive.writestr(f"series/slice-{index:06d}.dcm", slice_path.read_bytes())
            slice_path.unlink()
    return path
