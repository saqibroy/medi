"""Private object-storage boundary with a path-safe local implementation."""

from __future__ import annotations

import shutil
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlencode

import boto3
from botocore.exceptions import ClientError

from ..settings import get_settings


class StorageKeyError(ValueError):
    """Raised when an object key could escape the configured private root."""


DATA_CLASS_TAG_KEY = "medi-data-class"


@dataclass(frozen=True)
class StorageObjectSnapshot:
    """Version and digest evidence captured while reading one private object."""

    version_id: str
    checksum_sha256: str
    byte_size: int


@dataclass(frozen=True)
class StoragePurgeResult:
    """Value-free evidence returned by an exact-prefix operator purge."""

    object_count: int
    object_versions_deleted: int
    delete_markers_deleted: int


def _stream_sha256(stream: object, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    """Hash an object incrementally so large medical volumes stay bounded."""

    digest = hashlib.sha256()
    byte_size = 0
    while True:
        chunk = stream.read(chunk_size)  # type: ignore[attr-defined]
        if not chunk:
            break
        digest.update(chunk)
        byte_size += len(chunk)
    return digest.hexdigest(), byte_size


def _validate_object_key(key: str) -> str:
    if not key or "\x00" in key:
        raise StorageKeyError("Storage key is empty or invalid")
    object_key = PurePosixPath(key)
    if object_key.is_absolute() or ".." in object_key.parts:
        raise StorageKeyError("Storage key escapes the private root")
    return object_key.as_posix()


def storage_data_class(key: str) -> str:
    """Classify an object key for reviewed lifecycle and recovery policies."""

    safe_key = _validate_object_key(key)
    if "/quarantine/" in f"/{safe_key}":
        return "quarantine"
    if "/derived/preview/" in f"/{safe_key}":
        return "preview"
    if "/original/" in f"/{safe_key}":
        return "original"
    if "/mask/" in f"/{safe_key}":
        return "mask"
    if "/metadata/" in f"/{safe_key}" or safe_key.endswith(".metadata.json"):
        return "metadata"
    if "/export/" in f"/{safe_key}":
        return "export"
    return "unclassified"


class PrivateStorage(Protocol):
    def put_bytes(self, key: str, content: bytes) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def signed_get_url(self, key: str, expires_seconds: int) -> str: ...
    def snapshot(self, key: str) -> StorageObjectSnapshot: ...
    def purge_prefix_versions(self, prefix: str) -> StoragePurgeResult: ...


class LocalPrivateStorage:
    """Store object-keyed bytes below one non-public filesystem root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put_bytes(self, key: str, content: bytes) -> None:
        path = self.local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get_bytes(self, key: str) -> bytes:
        return self.local_path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self.local_path(key).is_file()

    def delete(self, key: str) -> None:
        path = self.local_path(key)
        if path.exists():
            path.unlink()

    def delete_prefix(self, prefix: str) -> None:
        path = self.local_path(prefix)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def purge_prefix_versions(self, prefix: str) -> StoragePurgeResult:
        path = self.local_path(prefix)
        if path.is_dir():
            object_count = sum(1 for item in path.rglob("*") if item.is_file())
        else:
            object_count = 1 if path.is_file() else 0
        self.delete_prefix(prefix)
        if path.exists():
            raise RuntimeError("Local deletion verification failed")
        return StoragePurgeResult(
            object_count=object_count,
            object_versions_deleted=object_count,
            delete_markers_deleted=0,
        )

    def local_path(self, key: str) -> Path:
        """Resolve a key below root, accepting only contained legacy paths."""

        if not key or "\x00" in key:
            raise StorageKeyError("Storage key is empty or invalid")
        supplied = Path(key)
        direct = supplied.resolve()
        if direct.is_relative_to(self.root):
            candidate = direct
        else:
            object_key = PurePosixPath(key)
            if object_key.is_absolute() or ".." in object_key.parts:
                raise StorageKeyError("Storage key escapes the private root")
            candidate = (self.root / Path(*object_key.parts)).resolve()
        if not candidate.is_relative_to(self.root):
            raise StorageKeyError("Storage key escapes the private root")
        return candidate

    def signed_get_url(self, key: str, expires_seconds: int) -> str:
        raise RuntimeError("Signed object URLs require the S3 storage backend")

    def snapshot(self, key: str) -> StorageObjectSnapshot:
        with self.local_path(key).open("rb") as stream:
            checksum, byte_size = _stream_sha256(stream)
        return StorageObjectSnapshot(
            version_id=f"local-sha256:{checksum}",
            checksum_sha256=checksum,
            byte_size=byte_size,
        )


class S3PrivateStorage:
    """Private S3 storage with mandatory server-side encryption on writes."""

    def __init__(
        self,
        bucket: str,
        region: str,
        server_side_encryption: str,
        kms_key_id: str | None = None,
        endpoint_url: str | None = None,
        client: object | None = None,
    ) -> None:
        self.bucket = bucket
        self.sse = server_side_encryption
        self.kms_key_id = kms_key_id
        self.client = client or boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

    def put_bytes(self, key: str, content: bytes) -> None:
        safe_key = _validate_object_key(key)
        arguments: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": safe_key,
            "Body": content,
            "ServerSideEncryption": self.sse,
            "Tagging": urlencode({DATA_CLASS_TAG_KEY: storage_data_class(safe_key)}),
        }
        if self.sse == "aws:kms" and self.kms_key_id:
            arguments["SSEKMSKeyId"] = self.kms_key_id
            arguments["BucketKeyEnabled"] = True
        self.client.put_object(**arguments)  # type: ignore[attr-defined]

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=_validate_object_key(key))  # type: ignore[attr-defined]
        return response["Body"].read()

    def snapshot(self, key: str) -> StorageObjectSnapshot:
        response = self.client.get_object(Bucket=self.bucket, Key=_validate_object_key(key))  # type: ignore[attr-defined]
        checksum, byte_size = _stream_sha256(response["Body"])
        version_id = str(response.get("VersionId") or f"sha256:{checksum}")
        return StorageObjectSnapshot(version_id=version_id, checksum_sha256=checksum, byte_size=byte_size)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=_validate_object_key(key))  # type: ignore[attr-defined]
            return True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_validate_object_key(key))  # type: ignore[attr-defined]

    def delete_prefix(self, prefix: str) -> None:
        safe_prefix = _validate_object_key(prefix).rstrip("/") + "/"
        paginator = self.client.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
        for page in paginator.paginate(Bucket=self.bucket, Prefix=safe_prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})  # type: ignore[attr-defined]

    def purge_prefix_versions(self, prefix: str) -> StoragePurgeResult:
        """Delete every version and marker below one trusted operator scope."""

        safe_prefix = _validate_object_key(prefix).rstrip("/") + "/"
        paginator = self.client.get_paginator("list_object_versions")  # type: ignore[attr-defined]
        object_versions = 0
        delete_markers = 0
        object_keys: set[str] = set()
        for page in paginator.paginate(Bucket=self.bucket, Prefix=safe_prefix):
            batch: list[dict[str, str]] = []
            for item in page.get("Versions", []):
                key = str(item["Key"])
                if not key.startswith(safe_prefix):
                    raise RuntimeError("S3 version listing escaped the deletion prefix")
                object_keys.add(key)
                object_versions += 1
                batch.append({"Key": key, "VersionId": str(item["VersionId"])})
            for item in page.get("DeleteMarkers", []):
                key = str(item["Key"])
                if not key.startswith(safe_prefix):
                    raise RuntimeError("S3 delete-marker listing escaped the deletion prefix")
                object_keys.add(key)
                delete_markers += 1
                batch.append({"Key": key, "VersionId": str(item["VersionId"])})
            for offset in range(0, len(batch), 1000):
                self.client.delete_objects(  # type: ignore[attr-defined]
                    Bucket=self.bucket,
                    Delete={"Objects": batch[offset : offset + 1000], "Quiet": True},
                )

        for page in paginator.paginate(Bucket=self.bucket, Prefix=safe_prefix):
            if page.get("Versions") or page.get("DeleteMarkers"):
                raise RuntimeError("S3 version deletion verification failed")
        return StoragePurgeResult(
            object_count=len(object_keys),
            object_versions_deleted=object_versions,
            delete_markers_deleted=delete_markers,
        )

    def signed_get_url(self, key: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url(  # type: ignore[attr-defined]
            "get_object",
            Params={"Bucket": self.bucket, "Key": _validate_object_key(key)},
            ExpiresIn=expires_seconds,
            HttpMethod="GET",
        )


def get_private_storage(local_root: Path | None = None) -> PrivateStorage:
    """Build the configured backend without exposing credentials to callers."""

    settings = get_settings()
    if settings.scan_storage_backend == "local":
        return LocalPrivateStorage(local_root or settings.scan_storage_root)
    return S3PrivateStorage(
        bucket=settings.scan_storage_bucket or "",
        region=settings.scan_storage_region or "",
        server_side_encryption=settings.scan_storage_sse,
        kms_key_id=settings.scan_storage_kms_key_id,
        endpoint_url=settings.scan_storage_endpoint_url,
    )


def scan_prefix(organization_id: object, project_id: object, scan_id: object) -> str:
    """Build a trusted tenant-scoped scan key prefix."""

    return f"org/{organization_id}/project/{project_id}/scan/{scan_id}"


def mask_key(organization_id: object, project_id: object, scan_id: object, annotation_id: object, slice_index: int) -> str:
    """Build a trusted tenant-scoped segmentation-mask object key."""

    return f"{scan_prefix(organization_id, project_id, scan_id)}/annotations/{annotation_id}/mask/{slice_index:06d}.png"
