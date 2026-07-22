"""Create immutable, value-free evidence before annotation history is purged."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter, defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, AnnotationHistory, AnnotationHistoryTombstone, Project, Scan
from ..settings import get_settings
from .dataset_release_service import canonical_json


DELETION_SOURCES = {"annotation_api", "data_lifecycle"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _keyed_hash(value: object) -> str:
    return hmac.new(
        get_settings().audit_signing_key.encode("utf-8"),
        canonical_json(value),
        hashlib.sha256,
    ).hexdigest()


def _history_material(history: AnnotationHistory) -> dict[str, object]:
    return {
        "id": history.id,
        "annotation_id": history.annotation_id,
        "changed_by_user_id": history.changed_by_user_id,
        "action": history.action,
        "changed_fields": sorted(history.changed_fields),
        "previous_values": history.previous_values,
        "new_values": history.new_values,
        "created_at": history.created_at,
    }


def _tombstone_material(tombstone: AnnotationHistoryTombstone) -> dict[str, object]:
    return {
        "id": tombstone.id,
        "organization_id": tombstone.organization_id,
        "project_id": tombstone.project_id,
        "scan_id": tombstone.scan_id,
        "annotation_id": tombstone.annotation_id,
        "deleted_by_user_id": tombstone.deleted_by_user_id,
        "deletion_source": tombstone.deletion_source,
        "history_entry_count": tombstone.history_entry_count,
        "action_counts": tombstone.action_counts,
        "changed_fields": tombstone.changed_fields,
        "first_history_at": tombstone.first_history_at,
        "last_history_at": tombstone.last_history_at,
        "history_lineage_hash": tombstone.history_lineage_hash,
        "deleted_at": tombstone.deleted_at,
    }


def retain_annotation_history_tombstones(
    db: Session,
    annotations: list[Annotation],
    *,
    deleted_by_user_id: UUID | None,
    deletion_source: str,
) -> list[AnnotationHistoryTombstone]:
    """Snapshot value-free lineage evidence before annotations cascade-delete."""

    if deletion_source not in DELETION_SOURCES:
        raise ValueError("unsupported annotation history deletion source")
    if not annotations:
        return []

    annotation_ids = [annotation.id for annotation in annotations]
    existing_ids = set(
        db.scalars(
            select(AnnotationHistoryTombstone.annotation_id).where(
                AnnotationHistoryTombstone.annotation_id.in_(annotation_ids)
            )
        )
    )
    histories = list(
        db.scalars(
            select(AnnotationHistory)
            .where(AnnotationHistory.annotation_id.in_(annotation_ids))
            .order_by(AnnotationHistory.annotation_id, AnnotationHistory.created_at, AnnotationHistory.id)
        )
    )
    histories_by_annotation: dict[UUID, list[AnnotationHistory]] = defaultdict(list)
    for history in histories:
        histories_by_annotation[history.annotation_id].append(history)

    scan_ids = {annotation.scan_id for annotation in annotations}
    scans_by_id = {scan.id: scan for scan in db.scalars(select(Scan).where(Scan.id.in_(scan_ids)))}
    project_ids = {scan.project_id for scan in scans_by_id.values() if scan.project_id is not None}
    projects_by_id = {project.id: project for project in db.scalars(select(Project).where(Project.id.in_(project_ids)))}
    deleted_at = _now()
    tombstones: list[AnnotationHistoryTombstone] = []

    for annotation in annotations:
        if annotation.id in existing_ids:
            continue
        scan = scans_by_id.get(annotation.scan_id)
        project = projects_by_id.get(scan.project_id) if scan is not None and scan.project_id is not None else None
        if scan is None or project is None:
            raise ValueError("annotation history tombstone requires a project-scoped scan")

        lineage = histories_by_annotation[annotation.id]
        action_counts = dict(sorted(Counter(history.action for history in lineage).items()))
        changed_fields = sorted({field for history in lineage for field in history.changed_fields})
        tombstone = AnnotationHistoryTombstone(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            scan_id=scan.id,
            annotation_id=annotation.id,
            deleted_by_user_id=deleted_by_user_id,
            deletion_source=deletion_source,
            history_entry_count=len(lineage),
            action_counts=action_counts,
            changed_fields=changed_fields,
            first_history_at=lineage[0].created_at if lineage else None,
            last_history_at=lineage[-1].created_at if lineage else None,
            history_lineage_hash=_keyed_hash([_history_material(history) for history in lineage]),
            integrity_hash="",
            deleted_at=deleted_at,
        )
        tombstone.integrity_hash = _keyed_hash(_tombstone_material(tombstone))
        db.add(tombstone)
        tombstones.append(tombstone)

    db.flush()
    return tombstones


def verify_tombstone_integrity(tombstone: AnnotationHistoryTombstone) -> bool:
    """Verify that stored value-free tombstone fields have not changed."""

    return hmac.compare_digest(tombstone.integrity_hash, _keyed_hash(_tombstone_material(tombstone)))
