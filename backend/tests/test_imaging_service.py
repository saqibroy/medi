"""Tests for Phase 2 imaging ingestion helpers."""

import gzip
from pathlib import Path

from backend.services.imaging_service import build_initial_scan_profile, build_nifti_scan_profile, detect_source_format, parse_nifti_volume
from backend.tests.fixtures.imaging import write_synthetic_nifti


def test_detect_source_format_from_extension_and_signature() -> None:
    assert detect_source_format("brain.nii.gz", b"not parsed yet") == "nifti"
    assert detect_source_format("slice.dcm", b"not parsed yet") == "dicom"
    assert detect_source_format("series.zip", b"not parsed yet") == "dicom_zip"
    assert detect_source_format("upload.bin", b"\0" * 128 + b"DICM") == "dicom"
    assert detect_source_format("upload.bin", b"PK\x03\x04archive") == "dicom_zip"
    assert detect_source_format("notes.txt", b"plain text") == "unknown"


def test_build_initial_scan_profile_sets_phase2_defaults() -> None:
    profile = build_initial_scan_profile("nifti", "MRI", 42, "project/scan/original/brain.nii.gz")

    assert profile["storage_key"] == "project/scan/original/brain.nii.gz"
    assert profile["source_format"] == "nifti"
    assert profile["ingestion_status"] == "ready"
    assert profile["depth"] == 42
    assert profile["width"] == 512
    assert profile["height"] == 512
    assert profile["spacing"] == [1.0, 1.0, 1.0]
    assert profile["imaging_metadata"]["parser_status"] == "not_parsed"


def test_parse_nifti_volume_reads_synthetic_fixture(tmp_path: Path) -> None:
    fixture_path = write_synthetic_nifti(tmp_path / "synthetic.nii.gz", width=5, height=4, depth=3, spacing=(0.5, 0.6, 1.2))

    volume = parse_nifti_volume(fixture_path.name, fixture_path.read_bytes())

    assert volume.width == 5
    assert volume.height == 4
    assert volume.depth == 3
    assert volume.spacing == (0.5, 0.6000000238418579, 1.2000000476837158)
    assert volume.voxels[:3] == (0.0, 1.0, 2.0)


def test_build_nifti_scan_profile_writes_preview_slices(tmp_path: Path) -> None:
    fixture_path = write_synthetic_nifti(tmp_path / "synthetic.nii.gz", width=5, height=4, depth=3)
    preview_root = tmp_path / "preview"

    profile = build_nifti_scan_profile(fixture_path.name, fixture_path.read_bytes(), "MRI", "storage/key", preview_root)

    assert profile["source_format"] == "nifti"
    assert profile["ingestion_status"] == "ready"
    assert profile["width"] == 5
    assert profile["height"] == 4
    assert profile["depth"] == 3
    assert profile["imaging_metadata"]["parser_status"] == "parsed"
    assert sorted(path.name for path in preview_root.glob("*.png")) == ["000000.png", "000001.png", "000002.png"]


def test_parse_nifti_volume_rejects_unsupported_header(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.nii.gz"
    with gzip.open(bad_path, "wb") as output:
        output.write(b"not-a-nifti")

    try:
        parse_nifti_volume(bad_path.name, bad_path.read_bytes())
    except ValueError as error:
        assert "too small" in str(error) or "could not be decompressed" in str(error)
    else:
        raise AssertionError("Expected invalid NIfTI payload to be rejected")
