"""Private object-storage boundary with a path-safe local implementation."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath


class StorageKeyError(ValueError):
    """Raised when an object key could escape the configured private root."""


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


def scan_prefix(organization_id: object, project_id: object, scan_id: object) -> str:
    """Build a trusted tenant-scoped scan key prefix."""

    return f"org/{organization_id}/project/{project_id}/scan/{scan_id}"


def mask_key(organization_id: object, project_id: object, scan_id: object, annotation_id: object, slice_index: int) -> str:
    """Build a trusted tenant-scoped segmentation-mask object key."""

    return f"{scan_prefix(organization_id, project_id, scan_id)}/annotations/{annotation_id}/mask/{slice_index:06d}.png"
