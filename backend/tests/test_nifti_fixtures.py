"""Tests for synthetic NIfTI fixture generation."""

import gzip
import struct
from pathlib import Path

from backend.tests.fixtures.imaging import write_synthetic_nifti


def test_write_synthetic_nifti_creates_valid_header_and_payload(tmp_path: Path) -> None:
    fixture_path = write_synthetic_nifti(tmp_path / "synthetic.nii.gz", width=5, height=4, depth=3, spacing=(0.5, 0.6, 1.2))

    with gzip.open(fixture_path, "rb") as source:
        payload = source.read()

    assert struct.unpack_from("<i", payload, 0)[0] == 348
    assert struct.unpack_from("<8h", payload, 40)[:4] == (3, 5, 4, 3)
    assert struct.unpack_from("<h", payload, 70)[0] == 16
    assert struct.unpack_from("<h", payload, 72)[0] == 32
    assert struct.unpack_from("<8f", payload, 76)[1:4] == (0.5, 0.6000000238418579, 1.2000000476837158)
    assert struct.unpack_from("<f", payload, 108)[0] == 352.0
    assert payload[344:348] == b"n+1\0"
    assert len(payload) == 352 + (5 * 4 * 3 * 4)
    assert struct.unpack_from("<3f", payload, 352) == (0.0, 1.0, 2.0)


def test_write_synthetic_nifti_rejects_invalid_dimensions(tmp_path: Path) -> None:
    try:
        write_synthetic_nifti(tmp_path / "bad.nii.gz", width=0)
    except ValueError as error:
        assert "dimensions must be positive" in str(error)
    else:
        raise AssertionError("Expected invalid dimensions to be rejected")
