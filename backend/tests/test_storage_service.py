"""Tests for tenant-safe private object keys and local storage."""

from pathlib import Path

import pytest

from backend.services.storage_service import LocalPrivateStorage, StorageKeyError, mask_key, scan_prefix


def test_local_private_storage_round_trip_and_prefix_delete(tmp_path: Path) -> None:
    storage = LocalPrivateStorage(tmp_path)
    prefix = scan_prefix("org-1", "project-1", "scan-1")
    key = f"{prefix}/original/scan.nii.gz"

    storage.put_bytes(key, b"synthetic")

    assert storage.exists(key)
    assert storage.get_bytes(key) == b"synthetic"
    assert storage.local_path(key).is_relative_to(tmp_path)
    storage.delete_prefix(prefix)
    assert not storage.exists(key)


@pytest.mark.parametrize("key", ["../outside", "/tmp/outside", "org/one/../../outside", ""])
def test_local_private_storage_rejects_unsafe_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(StorageKeyError):
        LocalPrivateStorage(tmp_path).put_bytes(key, b"private")


def test_object_key_builders_are_organization_scoped() -> None:
    assert scan_prefix("org-a", "project-a", "scan-a") == "org/org-a/project/project-a/scan/scan-a"
    assert mask_key("org-a", "project-a", "scan-a", "annotation-a", 7).startswith("org/org-a/project/project-a/scan/scan-a/")
