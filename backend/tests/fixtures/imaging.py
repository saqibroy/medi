"""Synthetic imaging fixtures for parser and ingestion tests."""

from __future__ import annotations

import gzip
import struct
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
