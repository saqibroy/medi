"""Private object-storage boundary with a path-safe local implementation."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

from ..settings import get_settings


class StorageKeyError(ValueError):
    """Raised when an object key could escape the configured private root."""


def _validate_object_key(key: str) -> str:
    if not key or "\x00" in key:
        raise StorageKeyError("Storage key is empty or invalid")
    object_key = PurePosixPath(key)
    if object_key.is_absolute() or ".." in object_key.parts:
        raise StorageKeyError("Storage key escapes the private root")
    return object_key.as_posix()


class PrivateStorage(Protocol):
    def put_bytes(self, key: str, content: bytes) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def signed_get_url(self, key: str, expires_seconds: int) -> str: ...


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
        arguments: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": _validate_object_key(key),
            "Body": content,
            "ServerSideEncryption": self.sse,
        }
        if self.sse == "aws:kms" and self.kms_key_id:
            arguments["SSEKMSKeyId"] = self.kms_key_id
            arguments["BucketKeyEnabled"] = True
        self.client.put_object(**arguments)  # type: ignore[attr-defined]

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=_validate_object_key(key))  # type: ignore[attr-defined]
        return response["Body"].read()

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
