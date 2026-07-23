"""Deterministic, immutable dataset release manifests."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Annotation, AnnotationHistory, DatasetRelease, DatasetReleaseArtifact, DatasetReleaseEvent, Label, Project, Scan, SegmentationMask, User
from .storage_service import PrivateStorage, StorageObjectSnapshot, get_private_storage


MANIFEST_SCHEMA_VERSION = "medi-dataset-release-v1"
RELEASE_BUILDER_VERSION = "medi-release-builder-v1"
ARTIFACT_SCHEMA_VERSION = "medi-portable-release-manifest-v1"
ARTIFACT_TYPE = "portable_manifest"
ARTIFACT_MEDIA_TYPE = "application/vnd.medi.dataset-release+json"
EXPORT_FORMAT_VERSIONS = {
    "coco": "medi-coco-v1",
    "csv": "medi-csv-v1",
    "native": "medi-native-v1",
    "segmentation_manifest": "medi-segmentation-v1",
    "yolo": "medi-yolo-v1",
}
REVOCATION_REASON_CODES = {"quality_issue", "source_withdrawn", "policy_change", "other"}


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.isoformat()


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _utc_text(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_json(value: object) -> bytes:
    """Serialize release material identically across supported databases."""

    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _scan_storage() -> PrivateStorage:
    from . import scan_service

    return get_private_storage(scan_service.STORAGE_ROOT)


def _mask_storage() -> PrivateStorage:
    from . import segmentation_mask_service

    return get_private_storage(segmentation_mask_service.MASK_STORAGE_ROOT)


def _artifact_storage() -> PrivateStorage:
    from . import scan_service

    return get_private_storage(scan_service.STORAGE_ROOT)


def _artifact_key(release: DatasetRelease) -> str:
    """Keep retained releases outside project/scan purge prefixes."""

    return (
        f"org/{release.organization_id}/retained-release/project/{release.project_id}/"
        f"release-artifact/{release.id}/{release.manifest_sha256}.json"
    )


def _artifact_response(artifact: DatasetReleaseArtifact) -> dict[str, object]:
    return {
        "id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "schema_version": artifact.schema_version,
        "media_type": artifact.media_type,
        "object_version_id": artifact.object_version_id,
        "checksum_sha256": artifact.checksum_sha256,
        "byte_size": artifact.byte_size,
        "created_by_user_id": artifact.created_by_user_id,
        "created_at": artifact.created_at,
    }


def _artifacts_by_release(db: Session, release_ids: Iterable[UUID]) -> dict[UUID, list[DatasetReleaseArtifact]]:
    ids = list(release_ids)
    grouped: dict[UUID, list[DatasetReleaseArtifact]] = defaultdict(list)
    if not ids:
        return grouped
    artifacts = db.scalars(
        select(DatasetReleaseArtifact)
        .where(DatasetReleaseArtifact.release_id.in_(ids))
        .order_by(DatasetReleaseArtifact.created_at, DatasetReleaseArtifact.id)
    )
    for artifact in artifacts:
        grouped[artifact.release_id].append(artifact)
    return grouped


def _stage_release_artifact(
    db: Session,
    release: DatasetRelease,
    created_by_user_id: UUID,
    storage: PrivateStorage,
) -> tuple[DatasetReleaseArtifact, bool]:
    artifact_bytes = canonical_json(release.manifest)
    checksum = hashlib.sha256(artifact_bytes).hexdigest()
    if checksum != release.manifest_sha256:
        raise RuntimeError("Dataset release manifest checksum changed before artifact creation")
    key = _artifact_key(release)
    wrote_object = False
    if not storage.exists(key):
        storage.put_bytes(key, artifact_bytes)
        wrote_object = True
    snapshot = storage.snapshot(key)
    if (
        snapshot.checksum_sha256 != checksum
        or snapshot.byte_size != len(artifact_bytes)
    ):
        if wrote_object:
            storage.delete(key)
        raise RuntimeError("Retained release artifact failed storage integrity verification")
    artifact = DatasetReleaseArtifact(
        release_id=release.id,
        organization_id=release.organization_id,
        project_id=release.project_id,
        artifact_type=ARTIFACT_TYPE,
        schema_version=ARTIFACT_SCHEMA_VERSION,
        media_type=ARTIFACT_MEDIA_TYPE,
        storage_key=key,
        object_version_id=snapshot.version_id,
        checksum_sha256=checksum,
        byte_size=snapshot.byte_size,
        created_by_user_id=created_by_user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(artifact)
    return artifact, wrote_object


def _object_evidence(snapshot: StorageObjectSnapshot, object_ref: str) -> dict[str, object]:
    return {
        "object_ref": object_ref,
        "version_id": snapshot.version_id,
        "checksum_sha256": snapshot.checksum_sha256,
        "byte_size": snapshot.byte_size,
    }


def _synthetic_scan_evidence(scan: Scan) -> dict[str, object]:
    profile = {
        "scan_id": scan.id,
        "modality": scan.modality,
        "num_slices": scan.num_slices,
        "width": scan.width,
        "height": scan.height,
        "depth": scan.depth,
        "spacing": scan.spacing,
        "source_format": scan.source_format,
    }
    checksum = sha256_json(profile)
    return {
        "object_ref": f"scan:{scan.id}:synthetic-profile",
        "version_id": f"synthetic-profile:{checksum}",
        "checksum_sha256": checksum,
        "byte_size": len(canonical_json(profile)),
    }


def _scan_object_evidence(scan: Scan, storage: PrivateStorage) -> dict[str, object]:
    if storage.exists(scan.file_path):
        return _object_evidence(storage.snapshot(scan.file_path), f"scan:{scan.id}:original")
    if scan.source_format == "synthetic":
        return _synthetic_scan_evidence(scan)
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A ready scan original is unavailable for release")


def _lineage_entry(history: AnnotationHistory) -> dict[str, object]:
    safe_lineage = {
        "history_id": history.id,
        "action": history.action,
        "changed_fields": sorted(history.changed_fields),
        "occurred_at": history.created_at,
    }
    serialized = _json_value(safe_lineage)
    assert isinstance(serialized, dict)
    return {**serialized, "event_sha256": sha256_json(safe_lineage)}


def _mask_evidence(mask: SegmentationMask, storage: PrivateStorage) -> dict[str, object]:
    if not storage.exists(mask.storage_key):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An approved segmentation mask is unavailable for release")
    snapshot = storage.snapshot(mask.storage_key)
    if snapshot.checksum_sha256 != mask.checksum_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An approved segmentation mask checksum does not match storage")
    return {
        **_object_evidence(snapshot, f"annotation:{mask.annotation_id}:mask:{mask.slice_index}"),
        "mask_id": str(mask.id),
        "slice_index": mask.slice_index,
        "width": mask.width,
        "height": mask.height,
        "encoding": mask.encoding,
    }


def _annotation_snapshot(
    annotation: Annotation,
    lineage: list[AnnotationHistory],
    mask: SegmentationMask | None,
    mask_storage: PrivateStorage,
) -> dict[str, object]:
    if annotation.annotation_type == "segmentation" and mask is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An approved segmentation annotation has no mask",
        )
    snapshot: dict[str, object] = {
        "annotation_id": str(annotation.id),
        "scan_id": str(annotation.scan_id),
        "label_id": str(annotation.label_id) if annotation.label_id else None,
        "label": annotation.label,
        "annotation_type": annotation.annotation_type,
        "coordinates": _json_value(annotation.coordinates),
        "slice_index": annotation.slice_index,
        "confidence_score": annotation.confidence_score,
        "review_status": annotation.review_status,
        "reviewed_at": _utc_text(annotation.reviewed_at),
        "reviewed_by_user_id": str(annotation.reviewed_by_user_id) if annotation.reviewed_by_user_id else None,
        "created_at": _utc_text(annotation.created_at),
        "updated_at": _utc_text(annotation.updated_at),
        "lineage": [_lineage_entry(entry) for entry in lineage],
        "segmentation_mask": _mask_evidence(mask, mask_storage) if mask is not None else None,
    }
    snapshot["revision_sha256"] = sha256_json(snapshot)
    return snapshot


def _release_content(
    db: Session,
    project: Project,
    scan_storage: PrivateStorage,
    mask_storage: PrivateStorage,
) -> dict[str, object]:
    labels = list(db.scalars(select(Label).where(Label.project_id == project.id).order_by(Label.name, Label.id)))
    scans = list(db.scalars(select(Scan).where(Scan.project_id == project.id, Scan.ingestion_status == "ready").order_by(Scan.id)))
    scan_ids = [scan.id for scan in scans]
    annotations = list(
        db.scalars(
            select(Annotation)
            .where(Annotation.scan_id.in_(scan_ids), Annotation.review_status == "approved")
            .order_by(Annotation.scan_id, Annotation.slice_index, Annotation.id)
        )
    ) if scan_ids else []
    annotation_ids = [annotation.id for annotation in annotations]
    histories = list(
        db.scalars(
            select(AnnotationHistory)
            .where(AnnotationHistory.annotation_id.in_(annotation_ids))
            .order_by(AnnotationHistory.annotation_id, AnnotationHistory.created_at, AnnotationHistory.id)
        )
    ) if annotation_ids else []
    masks = list(db.scalars(select(SegmentationMask).where(SegmentationMask.annotation_id.in_(annotation_ids)))) if annotation_ids else []
    histories_by_annotation: dict[UUID, list[AnnotationHistory]] = defaultdict(list)
    for history in histories:
        histories_by_annotation[history.annotation_id].append(history)
    masks_by_annotation = {mask.annotation_id: mask for mask in masks}
    annotations_by_scan: dict[UUID, list[Annotation]] = defaultdict(list)
    for annotation in annotations:
        annotations_by_scan[annotation.scan_id].append(annotation)

    scan_snapshots = []
    for scan in scans:
        scan_annotations = [
            _annotation_snapshot(annotation, histories_by_annotation[annotation.id], masks_by_annotation.get(annotation.id), mask_storage)
            for annotation in annotations_by_scan[scan.id]
        ]
        scan_snapshots.append(
            {
                "scan_id": str(scan.id),
                "modality": scan.modality,
                "source_format": scan.source_format,
                "num_slices": scan.num_slices,
                "deidentification_status": scan.deidentification_status,
                "metadata_profile_version": scan.deidentification_profile_version,
                "original_object": _scan_object_evidence(scan, scan_storage),
                "approved_annotations": scan_annotations,
            }
        )

    return {
        "project": {"project_id": str(project.id), "modality": project.modality},
        "labels": [{"label_id": str(label.id), "name": label.name, "color": label.color} for label in labels],
        "scans": scan_snapshots,
        "counts": {
            "labels": len(labels),
            "scans": len(scans),
            "approved_annotations": len(annotations),
            "segmentation_masks": len(masks),
        },
        "export_formats": [{"name": name, "version": version} for name, version in sorted(EXPORT_FORMAT_VERSIONS.items())],
        "release_builder_version": RELEASE_BUILDER_VERSION,
    }


def _events_by_release(db: Session, release_ids: Iterable[UUID]) -> dict[UUID, list[DatasetReleaseEvent]]:
    ids = list(release_ids)
    grouped: dict[UUID, list[DatasetReleaseEvent]] = defaultdict(list)
    if not ids:
        return grouped
    events = db.scalars(
        select(DatasetReleaseEvent)
        .where(DatasetReleaseEvent.release_id.in_(ids))
        .order_by(DatasetReleaseEvent.occurred_at, DatasetReleaseEvent.id)
    )
    for event in events:
        grouped[event.release_id].append(event)
    return grouped


def release_status(events: Iterable[DatasetReleaseEvent]) -> str:
    status_value = "active"
    for event in events:
        if event.action == "superseded":
            status_value = "superseded"
        elif event.action == "revoked":
            status_value = "revoked"
    return status_value


def _release_response(
    release: DatasetRelease,
    events: list[DatasetReleaseEvent],
    artifacts: list[DatasetReleaseArtifact],
    include_manifest: bool,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "id": release.id,
        "organization_id": release.organization_id,
        "project_id": release.project_id,
        "version": release.version,
        "schema_version": release.schema_version,
        "content_sha256": release.content_sha256,
        "manifest_sha256": release.manifest_sha256,
        "supersedes_release_id": release.supersedes_release_id,
        "created_by_user_id": release.created_by_user_id,
        "created_at": release.created_at,
        "status": release_status(events),
        "artifacts": [_artifact_response(artifact) for artifact in artifacts],
        "lifecycle": [
            {
                "id": event.id,
                "action": event.action,
                "reason_code": event.reason_code,
                "related_release_id": event.related_release_id,
                "actor_user_id": event.actor_user_id,
                "occurred_at": event.occurred_at,
            }
            for event in events
        ],
    }
    if include_manifest:
        response["manifest"] = release.manifest
    return response


def create_release(db: Session, project_id: UUID, current_user: User) -> dict[str, Any]:
    """Create one immutable release and supersede the previous active version."""

    project = db.scalar(
        select(Project)
        .where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
            Project.lifecycle_status != "deleted",
        )
        .with_for_update()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    previous = db.scalar(select(DatasetRelease).where(DatasetRelease.project_id == project.id).order_by(DatasetRelease.version.desc()).limit(1))
    version = (previous.version + 1) if previous is not None else 1
    release_id = uuid4()
    created_at = datetime.now(timezone.utc)
    content = _release_content(db, project, _scan_storage(), _mask_storage())
    content_sha256 = sha256_json(content)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "release_id": str(release_id),
        "project_id": str(project.id),
        "version": version,
        "created_at": _utc_text(created_at),
        "created_by_user_id": str(current_user.id),
        "supersedes_release_id": str(previous.id) if previous is not None else None,
        "content_sha256": content_sha256,
        "dataset": content,
    }
    release = DatasetRelease(
        id=release_id,
        organization_id=current_user.organization_id,
        project_id=project.id,
        version=version,
        schema_version=MANIFEST_SCHEMA_VERSION,
        content_sha256=content_sha256,
        manifest_sha256=sha256_json(manifest),
        manifest=manifest,
        supersedes_release_id=previous.id if previous is not None else None,
        created_by_user_id=current_user.id,
        created_at=created_at,
    )
    db.add(release)
    db.flush()
    artifact_storage = _artifact_storage()
    artifact, wrote_artifact = _stage_release_artifact(db, release, current_user.id, artifact_storage)
    created_event = DatasetReleaseEvent(
        release_id=release.id,
        organization_id=release.organization_id,
        actor_user_id=current_user.id,
        action="created",
        occurred_at=created_at,
    )
    db.add(created_event)
    if previous is not None:
        previous_events = _events_by_release(db, [previous.id])[previous.id]
        if release_status(previous_events) == "active":
            db.add(
                DatasetReleaseEvent(
                    release_id=previous.id,
                    organization_id=previous.organization_id,
                    actor_user_id=current_user.id,
                    action="superseded",
                    reason_code="superseded",
                    related_release_id=release.id,
                    occurred_at=created_at,
                )
            )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if wrote_artifact:
            artifact_storage.delete(artifact.storage_key)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A release version was created concurrently; retry") from error
    except Exception:
        db.rollback()
        if wrote_artifact:
            artifact_storage.delete(artifact.storage_key)
        raise
    db.refresh(release)
    events = _events_by_release(db, [release.id])[release.id]
    artifacts = _artifacts_by_release(db, [release.id])[release.id]
    return _release_response(release, events, artifacts, include_manifest=True)


def list_releases(db: Session, project_id: UUID, current_user: User) -> list[dict[str, Any]]:
    project = db.get(Project, project_id)
    if project is None or project.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    releases = list(db.scalars(select(DatasetRelease).where(DatasetRelease.project_id == project.id).order_by(DatasetRelease.version.desc())))
    events = _events_by_release(db, [release.id for release in releases])
    artifacts = _artifacts_by_release(db, [release.id for release in releases])
    return [_release_response(release, events[release.id], artifacts[release.id], include_manifest=False) for release in releases]


def get_release(db: Session, release_id: UUID, current_user: User) -> dict[str, Any]:
    release = db.get(DatasetRelease, release_id)
    if release is None or release.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset release not found")
    events = _events_by_release(db, [release.id])[release.id]
    artifacts = _artifacts_by_release(db, [release.id])[release.id]
    return _release_response(release, events, artifacts, include_manifest=True)


def materialize_release_artifact(db: Session, release_id: UUID, current_user: User) -> dict[str, object]:
    """Create the retained artifact for a legacy release, idempotently."""

    release = db.scalar(
        select(DatasetRelease)
        .where(
            DatasetRelease.id == release_id,
            DatasetRelease.organization_id == current_user.organization_id,
        )
        .with_for_update()
    )
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset release not found")
    existing = db.scalar(
        select(DatasetReleaseArtifact).where(
            DatasetReleaseArtifact.release_id == release.id,
            DatasetReleaseArtifact.artifact_type == ARTIFACT_TYPE,
        )
    )
    if existing is not None:
        return _artifact_response(existing)

    storage = _artifact_storage()
    artifact, wrote_artifact = _stage_release_artifact(db, release, current_user.id, storage)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        existing = db.scalar(
            select(DatasetReleaseArtifact).where(
                DatasetReleaseArtifact.release_id == release.id,
                DatasetReleaseArtifact.artifact_type == ARTIFACT_TYPE,
            )
        )
        if existing is not None:
            return _artifact_response(existing)
        if wrote_artifact:
            storage.delete(artifact.storage_key)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Release artifact was created concurrently; retry") from error
    except Exception:
        db.rollback()
        if wrote_artifact:
            storage.delete(artifact.storage_key)
        raise
    db.refresh(artifact)
    return _artifact_response(artifact)


def download_release_artifact(db: Session, release_id: UUID, current_user: User) -> tuple[DatasetReleaseArtifact, bytes]:
    """Return verified bytes only for a non-revoked, tenant-scoped release."""

    release = db.get(DatasetRelease, release_id)
    if release is None or release.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset release not found")
    events = _events_by_release(db, [release.id])[release.id]
    if release_status(events) == "revoked":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Revoked release artifacts cannot be downloaded")
    artifact = db.scalar(
        select(DatasetReleaseArtifact).where(
            DatasetReleaseArtifact.release_id == release.id,
            DatasetReleaseArtifact.artifact_type == ARTIFACT_TYPE,
        )
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retained release artifact not found")
    storage = _artifact_storage()
    if not storage.exists(artifact.storage_key):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Retained release artifact is unavailable")
    snapshot = storage.snapshot(artifact.storage_key)
    content = storage.get_bytes(artifact.storage_key)
    checksum = hashlib.sha256(content).hexdigest()
    if (
        snapshot.version_id != artifact.object_version_id
        or snapshot.checksum_sha256 != artifact.checksum_sha256
        or snapshot.byte_size != artifact.byte_size
        or checksum != artifact.checksum_sha256
        or len(content) != artifact.byte_size
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Retained release artifact integrity verification failed")
    return artifact, content


def revoke_release(db: Session, release_id: UUID, reason_code: str, current_user: User) -> dict[str, Any]:
    if reason_code not in REVOCATION_REASON_CODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsupported release revocation reason")
    release = db.get(DatasetRelease, release_id)
    if release is None or release.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset release not found")
    events = _events_by_release(db, [release.id])[release.id]
    if release_status(events) == "revoked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dataset release is already revoked")
    db.add(
        DatasetReleaseEvent(
            release_id=release.id,
            organization_id=release.organization_id,
            actor_user_id=current_user.id,
            action="revoked",
            reason_code=reason_code,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return get_release(db, release.id, current_user)
