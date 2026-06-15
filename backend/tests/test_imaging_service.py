"""Tests for Phase 2 imaging ingestion helpers."""

import gzip
import struct
import zipfile
from pathlib import Path

from backend.services import imaging_service
from backend.services.imaging_service import MAX_SERIES_SLICES, build_dicom_scan_profile, build_dicom_zip_scan_profile, build_initial_scan_profile, build_nifti_scan_profile, detect_source_format, parse_dicom_image, parse_dicom_zip, parse_nifti_volume, validate_upload_hint, validate_upload_size
from backend.tests.fixtures.imaging import _dicom_element, write_synthetic_dicom, write_synthetic_dicom_zip, write_synthetic_nifti


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
    assert profile["imaging_metadata"]["data_safety"] == "synthetic"
    assert profile["imaging_metadata"]["deidentification_status"] == "synthetic_no_phi"


def test_validate_upload_size_rejects_large_upload(monkeypatch) -> None:
    monkeypatch.setattr(imaging_service, "MAX_UPLOAD_BYTES", 10)

    try:
        validate_upload_size(b"x" * 11)
    except ValueError as error:
        assert "upload size limit" in str(error)
    else:
        raise AssertionError("Expected oversized upload to be rejected")


def test_validate_upload_hint_rejects_unsupported_extension_and_mime() -> None:
    try:
        validate_upload_hint("notes.txt", "text/plain")
    except ValueError as error:
        assert "Unsupported scan file type" in str(error)
    else:
        raise AssertionError("Expected unsupported extension to be rejected")

    try:
        validate_upload_hint("scan.dcm", "text/plain")
    except ValueError as error:
        assert "Unsupported scan MIME type" in str(error)
    else:
        raise AssertionError("Expected unsupported MIME type to be rejected")


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
    assert profile["imaging_metadata"]["deidentification_status"] == "user_supplied_deidentified_required"
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


def test_parse_dicom_image_reads_synthetic_fixture(tmp_path: Path) -> None:
    fixture_path = write_synthetic_dicom(tmp_path / "synthetic.dcm", width=6, height=4, spacing=(0.7, 0.9), slice_thickness=2.0)

    image = parse_dicom_image(fixture_path.read_bytes())

    assert image.width == 6
    assert image.height == 4
    assert image.spacing == (0.7, 0.9, 2.0)
    assert image.modality == "CT"
    assert image.window_center == 40.0
    assert image.window_width == 400.0
    assert image.phi_warnings == ()
    assert image.pixels[:3] == (0, 16, 32)


def test_parse_dicom_image_warns_about_phi_without_exposing_values(tmp_path: Path) -> None:
    fixture_path = write_synthetic_dicom(
        tmp_path / "phi.dcm",
        patient_name="Jane^Patient",
        patient_id="MRN-12345",
        accession_number="ACC-999",
    )

    image = parse_dicom_image(fixture_path.read_bytes())

    assert image.phi_warnings == ("AccessionNumber", "PatientName", "PatientID")
    assert "Jane" not in str(image)
    assert "MRN-12345" not in str(image)
    assert "ACC-999" not in str(image)


def test_parse_dicom_image_rejects_large_image(tmp_path: Path) -> None:
    payload = bytearray(b"\0" * 128 + b"DICM")
    payload += _dicom_element(0x0028, 0x0010, b"US", struct.pack("<H", 2048))
    payload += _dicom_element(0x0028, 0x0011, b"US", struct.pack("<H", 2048))
    payload += _dicom_element(0x0028, 0x0100, b"US", struct.pack("<H", 16))
    payload += _dicom_element(0x0028, 0x0103, b"US", struct.pack("<H", 0))
    payload += _dicom_element(0x7FE0, 0x0010, b"OW", b"\0\0")

    try:
        parse_dicom_image(bytes(payload))
    except ValueError as error:
        assert "preview limits" in str(error)
    else:
        raise AssertionError("Expected large DICOM image to be rejected")


def test_build_dicom_scan_profile_writes_preview_slice(tmp_path: Path) -> None:
    fixture_path = write_synthetic_dicom(tmp_path / "synthetic.dcm", width=6, height=4)
    preview_root = tmp_path / "preview"

    profile = build_dicom_scan_profile(fixture_path.read_bytes(), "CT", "storage/key", preview_root)

    assert profile["source_format"] == "dicom"
    assert profile["ingestion_status"] == "ready"
    assert profile["width"] == 6
    assert profile["height"] == 4
    assert profile["depth"] == 1
    assert profile["imaging_metadata"]["parser_status"] == "parsed"
    assert profile["imaging_metadata"]["deidentification_status"] == "no_phi_tags_detected"
    assert profile["imaging_metadata"]["phi_warnings"] == []
    assert sorted(path.name for path in preview_root.glob("*.png")) == ["000000.png"]


def test_parse_dicom_zip_reads_synthetic_series(tmp_path: Path) -> None:
    fixture_path = write_synthetic_dicom_zip(tmp_path / "series.zip", width=6, height=4, depth=3, spacing=(0.7, 0.9), slice_thickness=2.0)

    images = parse_dicom_zip(fixture_path.read_bytes())

    assert len(images) == 3
    assert {image.width for image in images} == {6}
    assert {image.height for image in images} == {4}
    assert images[0].spacing == (0.7, 0.9, 2.0)
    assert images[0].pixels[:3] == (0, 16, 32)


def test_build_dicom_zip_scan_profile_writes_preview_slices(tmp_path: Path) -> None:
    fixture_path = write_synthetic_dicom_zip(tmp_path / "series.zip", width=6, height=4, depth=3)
    preview_root = tmp_path / "preview"

    profile = build_dicom_zip_scan_profile(fixture_path.read_bytes(), "CT", "storage/key", preview_root)

    assert profile["source_format"] == "dicom_zip"
    assert profile["ingestion_status"] == "ready"
    assert profile["width"] == 6
    assert profile["height"] == 4
    assert profile["depth"] == 3
    assert profile["imaging_metadata"]["parser_status"] == "parsed"
    assert profile["imaging_metadata"]["deidentification_status"] == "no_phi_tags_detected"
    assert profile["imaging_metadata"]["preview_slice_count"] == 3
    assert sorted(path.name for path in preview_root.glob("*.png")) == ["000000.png", "000001.png", "000002.png"]


def test_parse_dicom_zip_rejects_unsafe_paths(tmp_path: Path) -> None:
    dicom_path = write_synthetic_dicom(tmp_path / "slice.dcm")
    zip_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../slice.dcm", dicom_path.read_bytes())

    try:
        parse_dicom_zip(zip_path.read_bytes())
    except ValueError as error:
        assert "unsafe path" in str(error)
    else:
        raise AssertionError("Expected unsafe zip member to be rejected")


def test_parse_dicom_zip_rejects_too_many_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "too-many.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for index in range(MAX_SERIES_SLICES + 1):
            archive.writestr(f"slice-{index:06d}.txt", b"not dicom")

    try:
        parse_dicom_zip(zip_path.read_bytes())
    except ValueError as error:
        assert "too many files" in str(error)
    else:
        raise AssertionError("Expected oversized DICOM zip to be rejected")
