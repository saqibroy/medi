"""Tests for tenant-safe private object keys and local storage."""

from pathlib import Path

import pytest

from backend.services.storage_service import LocalPrivateStorage, S3PrivateStorage, StorageKeyError, mask_key, scan_prefix


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class FakePaginator:
    def __init__(self, client: "FakeS3Client") -> None:
        self.client = client

    def paginate(self, **arguments: object) -> list[dict[str, list[dict[str, str]]]]:
        prefix = str(arguments["Prefix"])
        return [{"Contents": [{"Key": key} for key in self.client.objects if key.startswith(prefix)]}]


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.last_put: dict[str, object] = {}
        self.last_presign: dict[str, object] = {}

    def put_object(self, **arguments: object) -> None:
        self.last_put = arguments
        self.objects[str(arguments["Key"])] = arguments["Body"]  # type: ignore[assignment]

    def get_object(self, **arguments: object) -> dict[str, FakeBody]:
        return {"Body": FakeBody(self.objects[str(arguments["Key"])])}

    def head_object(self, **arguments: object) -> None:
        if str(arguments["Key"]) not in self.objects:
            raise AssertionError("Test only calls head_object for existing keys")

    def delete_object(self, **arguments: object) -> None:
        self.objects.pop(str(arguments["Key"]), None)

    def get_paginator(self, operation_name: str) -> FakePaginator:
        assert operation_name == "list_objects_v2"
        return FakePaginator(self)

    def delete_objects(self, **arguments: object) -> None:
        delete = arguments["Delete"]
        assert isinstance(delete, dict)
        for item in delete["Objects"]:
            self.objects.pop(str(item["Key"]), None)

    def generate_presigned_url(self, method: str, **arguments: object) -> str:
        self.last_presign = {"method": method, **arguments}
        return "https://signed.example/preview"


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


def test_s3_storage_requires_kms_on_write_and_generates_short_lived_get_url() -> None:
    client = FakeS3Client()
    storage = S3PrivateStorage(
        bucket="medi-private",
        region="eu-central-1",
        server_side_encryption="aws:kms",
        kms_key_id="kms-key-id",
        client=client,
    )
    key = "org/org-a/project/project-a/scan/scan-a/derived/preview/000000.png"

    storage.put_bytes(key, b"png")
    url = storage.signed_get_url(key, 300)

    assert storage.get_bytes(key) == b"png"
    assert client.last_put["ServerSideEncryption"] == "aws:kms"
    assert client.last_put["SSEKMSKeyId"] == "kms-key-id"
    assert client.last_put["BucketKeyEnabled"] is True
    assert url == "https://signed.example/preview"
    assert client.last_presign["method"] == "get_object"
    assert client.last_presign["ExpiresIn"] == 300


def test_s3_storage_deletes_only_the_requested_prefix() -> None:
    client = FakeS3Client()
    storage = S3PrivateStorage("bucket", "region", "AES256", client=client)
    selected_prefix = "org/org-a/project/project-a/scan/scan-a/derived/preview"
    selected_key = f"{selected_prefix}/000000.png"
    retained_key = "org/org-a/project/project-a/scan/scan-b/derived/preview/000000.png"
    storage.put_bytes(selected_key, b"delete")
    storage.put_bytes(retained_key, b"retain")

    storage.delete_prefix(selected_prefix)

    assert selected_key not in client.objects
    assert client.objects[retained_key] == b"retain"


def test_s3_storage_rejects_unsafe_key_before_client_call() -> None:
    client = FakeS3Client()
    storage = S3PrivateStorage("bucket", "region", "AES256", client=client)

    with pytest.raises(StorageKeyError):
        storage.put_bytes("../escape", b"private")
    assert client.last_put == {}
