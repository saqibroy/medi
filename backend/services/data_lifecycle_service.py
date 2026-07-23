"""Retention, legal-hold, deletion approval, and operator execution controls."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Annotation,
    AnnotationHistory,
    AnnotationHistoryTombstone,
    DataDeletionEvent,
    DataDeletionReceipt,
    DataDeletionRequest,
    DataRetentionPolicy,
    DatasetRelease,
    DatasetReleaseArtifact,
    DatasetReleaseEvent,
    Label,
    LegalHold,
    LegalHoldEvent,
    Organization,
    Project,
    Scan,
    SecurityAuditEvent,
    SegmentationMask,
    User,
)
from .audit_service import calculate_integrity_hash
from .annotation_history_tombstone_service import retain_annotation_history_tombstones
from .dataset_release_service import release_status, sha256_json
from .storage_service import StoragePurgeResult, get_private_storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _event_groups(events: Iterable[Any], key_name: str) -> dict[UUID, list[Any]]:
    grouped: dict[UUID, list[Any]] = defaultdict(list)
    for event in events:
        grouped[getattr(event, key_name)].append(event)
    return grouped


def create_retention_policy(db: Session, payload: Any, current_user: User) -> DataRetentionPolicy:
    organization = db.scalar(
        select(Organization).where(Organization.id == current_user.organization_id).with_for_update()
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    previous_version = db.scalar(
        select(func.max(DataRetentionPolicy.version)).where(
            DataRetentionPolicy.organization_id == current_user.organization_id
        )
    )
    policy = DataRetentionPolicy(
        organization_id=current_user.organization_id,
        version=(previous_version or 0) + 1,
        created_by_user_id=current_user.id,
        created_at=_now(),
        **payload.model_dump(),
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def list_retention_policies(db: Session, current_user: User) -> list[DataRetentionPolicy]:
    return list(
        db.scalars(
            select(DataRetentionPolicy)
            .where(DataRetentionPolicy.organization_id == current_user.organization_id)
            .order_by(DataRetentionPolicy.version.desc())
        )
    )


def current_retention_policy(db: Session, organization_id: UUID) -> DataRetentionPolicy:
    policy = db.scalar(
        select(DataRetentionPolicy)
        .where(DataRetentionPolicy.organization_id == organization_id)
        .order_by(DataRetentionPolicy.version.desc())
        .limit(1)
    )
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An approved organization retention policy is required",
        )
    return policy


def _scope_context(db: Session, organization_id: UUID, scope_type: str, scope_id: UUID) -> dict[str, UUID | None]:
    if scope_type == "organization":
        if scope_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Governance scope not found")
        return {"organization_id": organization_id, "project_id": None, "scan_id": None}
    if scope_type == "project":
        project = db.scalar(
            select(Project).where(
                Project.id == scope_id,
                Project.organization_id == organization_id,
                Project.lifecycle_status != "deleted",
            )
        )
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Governance scope not found")
        return {"organization_id": organization_id, "project_id": project.id, "scan_id": None}
    if scope_type == "scan":
        scan = db.scalar(
            select(Scan)
            .join(Project, Scan.project_id == Project.id)
            .where(Scan.id == scope_id, Project.organization_id == organization_id, Project.lifecycle_status != "deleted")
        )
        if scan is None or scan.project_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Governance scope not found")
        return {"organization_id": organization_id, "project_id": scan.project_id, "scan_id": scan.id}
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsupported governance scope")


def _hold_events(db: Session, hold_ids: Iterable[UUID]) -> dict[UUID, list[LegalHoldEvent]]:
    ids = list(hold_ids)
    if not ids:
        return defaultdict(list)
    events = db.scalars(
        select(LegalHoldEvent)
        .where(LegalHoldEvent.hold_id.in_(ids))
        .order_by(LegalHoldEvent.occurred_at, LegalHoldEvent.id)
    )
    return _event_groups(events, "hold_id")


def hold_status(events: Iterable[LegalHoldEvent]) -> str:
    return "released" if any(event.action == "released" for event in events) else "active"


def _hold_response(hold: LegalHold, events: list[LegalHoldEvent]) -> dict[str, Any]:
    return {
        "id": hold.id,
        "organization_id": hold.organization_id,
        "scope_type": hold.scope_type,
        "scope_id": hold.scope_id,
        "reason_code": hold.reason_code,
        "approval_reference": hold.approval_reference,
        "created_by_user_id": hold.created_by_user_id,
        "created_at": hold.created_at,
        "status": hold_status(events),
        "events": events,
    }


def create_legal_hold(db: Session, payload: Any, current_user: User) -> dict[str, Any]:
    _scope_context(db, current_user.organization_id, payload.scope_type, payload.scope_id)
    holds = list(
        db.scalars(
            select(LegalHold).where(
                LegalHold.organization_id == current_user.organization_id,
                LegalHold.scope_type == payload.scope_type,
                LegalHold.scope_id == payload.scope_id,
            )
        )
    )
    events_by_hold = _hold_events(db, [hold.id for hold in holds])
    if any(hold_status(events_by_hold[hold.id]) == "active" for hold in holds):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active legal hold already covers this scope")
    occurred_at = _now()
    hold = LegalHold(
        organization_id=current_user.organization_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        reason_code=payload.reason_code,
        approval_reference=payload.approval_reference,
        created_by_user_id=current_user.id,
        created_at=occurred_at,
    )
    db.add(hold)
    db.flush()
    event = LegalHoldEvent(
        hold_id=hold.id,
        organization_id=hold.organization_id,
        action="applied",
        actor_user_id=current_user.id,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(hold)
    return _hold_response(hold, [event])


def list_legal_holds(db: Session, current_user: User) -> list[dict[str, Any]]:
    holds = list(
        db.scalars(
            select(LegalHold)
            .where(LegalHold.organization_id == current_user.organization_id)
            .order_by(LegalHold.created_at.desc(), LegalHold.id.desc())
        )
    )
    events = _hold_events(db, [hold.id for hold in holds])
    return [_hold_response(hold, events[hold.id]) for hold in holds]


def release_legal_hold(db: Session, hold_id: UUID, current_user: User) -> dict[str, Any]:
    hold = db.get(LegalHold, hold_id)
    if hold is None or hold.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal hold not found")
    events = _hold_events(db, [hold.id])[hold.id]
    if hold_status(events) == "released":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Legal hold is already released")
    if hold.created_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A different administrator must release the legal hold")
    event = LegalHoldEvent(
        hold_id=hold.id,
        organization_id=hold.organization_id,
        action="released",
        actor_user_id=current_user.id,
        occurred_at=_now(),
    )
    db.add(event)
    db.commit()
    return _hold_response(hold, [*events, event])


def _applicable_active_holds(
    db: Session,
    organization_id: UUID,
    scope_type: str,
    scope_id: UUID,
) -> list[LegalHold]:
    context = _scope_context(db, organization_id, scope_type, scope_id)
    project_scan_ids: set[UUID] = set()
    if scope_type == "project":
        project_scan_ids = set(db.scalars(select(Scan.id).where(Scan.project_id == scope_id)))
    holds = list(db.scalars(select(LegalHold).where(LegalHold.organization_id == organization_id)))
    events = _hold_events(db, [hold.id for hold in holds])
    applicable = []
    for hold in holds:
        if hold_status(events[hold.id]) != "active":
            continue
        matches = hold.scope_type == "organization" and hold.scope_id == organization_id
        matches = matches or (hold.scope_type == "project" and hold.scope_id == context["project_id"])
        matches = matches or (hold.scope_type == "scan" and hold.scope_id == context["scan_id"])
        matches = matches or (scope_type == "project" and hold.scope_type == "scan" and hold.scope_id in project_scan_ids)
        if matches:
            applicable.append(hold)
    return applicable


def _scope_rows(db: Session, organization_id: UUID, scope_type: str, scope_id: UUID) -> tuple[Project, list[Scan]]:
    context = _scope_context(db, organization_id, scope_type, scope_id)
    project = db.get(Project, context["project_id"])
    assert project is not None
    if scope_type == "scan":
        scan = db.get(Scan, scope_id)
        assert scan is not None
        return project, [scan]
    return project, list(db.scalars(select(Scan).where(Scan.project_id == project.id)))


def inventory_scope(db: Session, organization_id: UUID, scope_type: str, scope_id: UUID) -> dict[str, int]:
    project, scans = _scope_rows(db, organization_id, scope_type, scope_id)
    scan_ids = [scan.id for scan in scans]
    annotation_ids = list(db.scalars(select(Annotation.id).where(Annotation.scan_id.in_(scan_ids)))) if scan_ids else []
    release_count = 0
    release_ids: list[UUID] = []
    if scope_type == "project":
        release_ids = list(db.scalars(select(DatasetRelease.id).where(DatasetRelease.project_id == project.id)))
        release_count = len(release_ids)
    else:
        releases = list(db.scalars(select(DatasetRelease).where(DatasetRelease.project_id == project.id)))
        release_ids = [
            release.id
            for release in releases
            if any(scan.get("scan_id") == str(scope_id) for scan in release.manifest.get("dataset", {}).get("scans", []))
        ]
        release_count = len(release_ids)
    release_artifact_count = 0
    if release_ids:
        release_artifact_count = db.scalar(
            select(func.count())
            .select_from(DatasetReleaseArtifact)
            .where(DatasetReleaseArtifact.release_id.in_(release_ids))
        ) or 0
    history_count = (
        db.scalar(select(func.count()).select_from(AnnotationHistory).where(AnnotationHistory.annotation_id.in_(annotation_ids))) or 0
        if annotation_ids
        else 0
    )
    tombstone_count = (
        db.scalar(select(func.count()).select_from(AnnotationHistoryTombstone).where(AnnotationHistoryTombstone.scan_id.in_(scan_ids))) or 0
        if scan_ids
        else 0
    )
    mask_count = (
        db.scalar(select(func.count()).select_from(SegmentationMask).where(SegmentationMask.annotation_id.in_(annotation_ids))) or 0
        if annotation_ids
        else 0
    )
    label_count = (
        db.scalar(select(func.count()).select_from(Label).where(Label.project_id == project.id)) or 0
        if scope_type == "project"
        else 0
    )
    original_references = sum(1 for scan in scans if scan.source_format != "synthetic")
    return {
        "projects": 1 if scope_type == "project" else 0,
        "scans": len(scans),
        "labels": label_count,
        "annotations": len(annotation_ids),
        "annotation_history": history_count,
        "annotation_history_tombstones": tombstone_count,
        "segmentation_masks": mask_count,
        "dataset_releases": release_count,
        "dataset_release_artifacts": release_artifact_count,
        "object_references": original_references + mask_count,
    }


def _earliest_execution(
    db: Session,
    project: Project,
    scans: list[Scan],
    scope_type: str,
    policy: DataRetentionPolicy,
) -> datetime:
    data_days = max(policy.original_minimum_days, policy.mask_minimum_days, policy.metadata_minimum_days)
    candidates = [_aware(project.created_at) + timedelta(days=data_days)]
    candidates.extend(_aware(scan.created_at) + timedelta(days=data_days) for scan in scans)
    if scope_type == "project":
        releases = db.scalars(select(DatasetRelease).where(DatasetRelease.project_id == project.id))
    else:
        scan_id = scans[0].id
        releases = (
            release
            for release in db.scalars(select(DatasetRelease).where(DatasetRelease.project_id == project.id))
            if any(scan.get("scan_id") == str(scan_id) for scan in release.manifest.get("dataset", {}).get("scans", []))
        )
    candidates.extend(
        _aware(release.created_at) + timedelta(days=policy.dataset_release_minimum_days)
        for release in releases
    )
    return max(candidates)


def _deletion_events(db: Session, request_ids: Iterable[UUID]) -> dict[UUID, list[DataDeletionEvent]]:
    ids = list(request_ids)
    if not ids:
        return defaultdict(list)
    events = db.scalars(
        select(DataDeletionEvent)
        .where(DataDeletionEvent.request_id.in_(ids))
        .order_by(DataDeletionEvent.occurred_at, DataDeletionEvent.id)
    )
    return _event_groups(events, "request_id")


def deletion_status(events: Iterable[DataDeletionEvent]) -> str:
    actions = {event.action for event in events}
    for action in ("verified", "executed", "failed", "cancelled", "approved", "requested"):
        if action in actions:
            return action
    return "requested"


def _request_response(request: DataDeletionRequest, events: list[DataDeletionEvent]) -> dict[str, Any]:
    return {
        "id": request.id,
        "organization_id": request.organization_id,
        "scope_type": request.scope_type,
        "scope_id": request.scope_id,
        "reason_code": request.reason_code,
        "approval_reference": request.approval_reference,
        "retention_policy_id": request.retention_policy_id,
        "retention_policy_version": request.retention_policy_version,
        "inventory": request.inventory,
        "earliest_execute_at": request.earliest_execute_at,
        "requested_by_user_id": request.requested_by_user_id,
        "created_at": request.created_at,
        "status": deletion_status(events),
        "events": events,
        "receipt": request.receipt,
    }


def create_deletion_request(db: Session, payload: Any, current_user: User) -> dict[str, Any]:
    policy = current_retention_policy(db, current_user.organization_id)
    project, scans = _scope_rows(db, current_user.organization_id, payload.scope_type, payload.scope_id)
    existing = list(
        db.scalars(
            select(DataDeletionRequest).where(
                DataDeletionRequest.organization_id == current_user.organization_id,
                DataDeletionRequest.scope_type == payload.scope_type,
                DataDeletionRequest.scope_id == payload.scope_id,
            )
        )
    )
    existing_events = _deletion_events(db, [request.id for request in existing])
    if any(deletion_status(existing_events[request.id]) in {"requested", "approved"} for request in existing):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active deletion request already covers this scope")
    occurred_at = _now()
    request = DataDeletionRequest(
        organization_id=current_user.organization_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        reason_code=payload.reason_code,
        approval_reference=payload.approval_reference,
        retention_policy_id=policy.id,
        retention_policy_version=policy.version,
        inventory=inventory_scope(db, current_user.organization_id, payload.scope_type, payload.scope_id),
        earliest_execute_at=_earliest_execution(db, project, scans, payload.scope_type, policy),
        requested_by_user_id=current_user.id,
        created_at=occurred_at,
    )
    db.add(request)
    db.flush()
    event = DataDeletionEvent(
        request_id=request.id,
        organization_id=request.organization_id,
        action="requested",
        actor_user_id=current_user.id,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(request)
    return _request_response(request, [event])


def list_deletion_requests(db: Session, current_user: User) -> list[dict[str, Any]]:
    requests = list(
        db.scalars(
            select(DataDeletionRequest)
            .where(DataDeletionRequest.organization_id == current_user.organization_id)
            .order_by(DataDeletionRequest.created_at.desc(), DataDeletionRequest.id.desc())
        )
    )
    events = _deletion_events(db, [request.id for request in requests])
    return [_request_response(request, events[request.id]) for request in requests]


def get_deletion_request(db: Session, request_id: UUID, current_user: User) -> dict[str, Any]:
    request = db.get(DataDeletionRequest, request_id)
    if request is None or request.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion request not found")
    events = _deletion_events(db, [request.id])[request.id]
    return _request_response(request, events)


def approve_deletion_request(db: Session, request_id: UUID, current_user: User) -> dict[str, Any]:
    request = db.get(DataDeletionRequest, request_id)
    if request is None or request.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion request not found")
    events = _deletion_events(db, [request.id])[request.id]
    if deletion_status(events) != "requested":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deletion request is not awaiting approval")
    if request.requested_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A different administrator must approve deletion")
    if _now() < _aware(request.earliest_execute_at):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The approved minimum retention period has not elapsed")
    if _applicable_active_holds(db, request.organization_id, request.scope_type, request.scope_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active legal hold blocks deletion")
    event = DataDeletionEvent(
        request_id=request.id,
        organization_id=request.organization_id,
        action="approved",
        actor_user_id=current_user.id,
        occurred_at=_now(),
    )
    db.add(event)
    db.commit()
    return _request_response(request, [*events, event])


def cancel_deletion_request(db: Session, request_id: UUID, current_user: User) -> dict[str, Any]:
    request = db.get(DataDeletionRequest, request_id)
    if request is None or request.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion request not found")
    events = _deletion_events(db, [request.id])[request.id]
    if deletion_status(events) not in {"requested", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deletion request cannot be cancelled")
    event = DataDeletionEvent(
        request_id=request.id,
        organization_id=request.organization_id,
        action="cancelled",
        actor_user_id=current_user.id,
        occurred_at=_now(),
    )
    db.add(event)
    db.commit()
    return _request_response(request, [*events, event])


def _release_ids_for_scope(db: Session, request: DataDeletionRequest, project_id: UUID) -> list[UUID]:
    releases = list(db.scalars(select(DatasetRelease).where(DatasetRelease.project_id == project_id)))
    if request.scope_type == "project":
        return [release.id for release in releases]
    return [
        release.id
        for release in releases
        if any(scan.get("scan_id") == str(request.scope_id) for scan in release.manifest.get("dataset", {}).get("scans", []))
    ]


def _revoke_releases(db: Session, request: DataDeletionRequest, project_id: UUID, operator_user_id: UUID) -> int:
    release_ids = _release_ids_for_scope(db, request, project_id)
    if not release_ids:
        return 0
    events = _event_groups(
        db.scalars(
            select(DatasetReleaseEvent)
            .where(DatasetReleaseEvent.release_id.in_(release_ids))
            .order_by(DatasetReleaseEvent.occurred_at, DatasetReleaseEvent.id)
        ),
        "release_id",
    )
    revoked = 0
    for release_id in release_ids:
        if release_status(events[release_id]) == "revoked":
            continue
        db.add(
            DatasetReleaseEvent(
                release_id=release_id,
                organization_id=request.organization_id,
                actor_user_id=operator_user_id,
                action="revoked",
                reason_code="source_withdrawn",
                occurred_at=_now(),
            )
        )
        revoked += 1
    return revoked


def _purge_storage(request: DataDeletionRequest, project_id: UUID) -> StoragePurgeResult:
    from . import scan_service, segmentation_mask_service
    from ..settings import get_settings

    prefix = f"org/{request.organization_id}/project/{project_id}"
    if request.scope_type == "scan":
        prefix += f"/scan/{request.scope_id}"
    settings = get_settings()
    scan_storage = get_private_storage(scan_service.STORAGE_ROOT)
    scan_result = scan_storage.purge_prefix_versions(prefix)
    if settings.scan_storage_backend == "s3":
        return scan_result
    mask_storage = get_private_storage(segmentation_mask_service.MASK_STORAGE_ROOT)
    mask_result = mask_storage.purge_prefix_versions(prefix)
    return StoragePurgeResult(
        object_count=scan_result.object_count + mask_result.object_count,
        object_versions_deleted=scan_result.object_versions_deleted + mask_result.object_versions_deleted,
        delete_markers_deleted=scan_result.delete_markers_deleted + mask_result.delete_markers_deleted,
    )


def _operator_audit(
    request: DataDeletionRequest,
    operator_user_id: UUID,
    result: str,
    occurred_at: datetime,
) -> SecurityAuditEvent:
    from ..settings import get_settings

    event = SecurityAuditEvent(
        id=uuid4(),
        organization_id=request.organization_id,
        actor_user_id=operator_user_id,
        actor_session_id=None,
        action="deletion_request.execute",
        result=result,
        target_type="deletion_request",
        target_id=request.id,
        request_id=None,
        details={},
        occurred_at=occurred_at,
        integrity_hash="",
    )
    event.integrity_hash = calculate_integrity_hash(event, get_settings().audit_signing_key)
    return event


def execute_deletion_request(
    db: Session,
    request_id: UUID,
    operator_user_id: UUID,
    confirmation: str,
) -> DataDeletionReceipt:
    """Execute one approved request from the separately enabled operator CLI."""

    if confirmation != str(request_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deletion confirmation does not match request ID")
    request = db.get(DataDeletionRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion request not found")
    operator = db.get(User, operator_user_id)
    if operator is None or not operator.is_active or operator.role != "admin" or operator.organization_id != request.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A scoped active administrator operator is required")
    events = _deletion_events(db, [request.id])[request.id]
    if deletion_status(events) != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deletion request is not approved")
    approved_event = next(event for event in events if event.action == "approved")
    if operator.id in {request.requested_by_user_id, approved_event.actor_user_id}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The operator must differ from requester and approver")
    if _now() < _aware(request.earliest_execute_at):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The approved minimum retention period has not elapsed")
    if _applicable_active_holds(db, request.organization_id, request.scope_type, request.scope_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active legal hold blocks deletion")

    policy = db.get(DataRetentionPolicy, request.retention_policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deletion policy snapshot is unavailable")
    project, scans = _scope_rows(db, request.organization_id, request.scope_type, request.scope_id)
    live_inventory = inventory_scope(db, request.organization_id, request.scope_type, request.scope_id)
    try:
        purge = _purge_storage(request, project.id)
        revoked_releases = _revoke_releases(db, request, project.id, operator.id)
        annotations = list(
            db.scalars(select(Annotation).where(Annotation.scan_id.in_([scan.id for scan in scans])))
        )
        retained_tombstones = retain_annotation_history_tombstones(
            db,
            annotations,
            deleted_by_user_id=operator.id,
            deletion_source="data_lifecycle",
        )
        if request.scope_type == "scan":
            db.delete(scans[0])
        else:
            for scan in scans:
                db.delete(scan)
            db.flush()
            for label in list(db.scalars(select(Label).where(Label.project_id == project.id))):
                db.delete(label)
            project.name = f"Deleted project {str(project.id)[:8]}"
            project.description = None
            project.lifecycle_status = "deleted"
            project.deleted_at = _now()
        completed_at = _now()
        receipt_id = uuid4()
        deleted_counts = {
            "project_tombstones": 1 if request.scope_type == "project" else 0,
            "scans": live_inventory["scans"],
            "labels": live_inventory["labels"],
            "annotations": live_inventory["annotations"],
            "annotation_history": live_inventory["annotation_history"],
            "annotation_history_tombstones_retained": (
                live_inventory["annotation_history_tombstones"] + len(retained_tombstones)
            ),
            "segmentation_masks": live_inventory["segmentation_masks"],
            "dataset_release_artifacts_retained": live_inventory["dataset_release_artifacts"],
        }
        receipt_material = {
            "id": receipt_id,
            "request_id": request.id,
            "organization_id": request.organization_id,
            "scope_type": request.scope_type,
            "scope_id": request.scope_id,
            "deleted_counts": deleted_counts,
            "object_versions_deleted": purge.object_versions_deleted,
            "delete_markers_deleted": purge.delete_markers_deleted,
            "revoked_releases": revoked_releases,
            "backup_disposition": "expires_per_policy",
            "backup_expires_at": completed_at + timedelta(days=policy.backup_retention_days),
            "approved_by_user_id": approved_event.actor_user_id,
            "operator_user_id": operator.id,
            "completed_at": completed_at,
        }
        receipt = DataDeletionReceipt(**receipt_material, receipt_sha256=sha256_json(receipt_material))
        db.add(receipt)
        db.add_all(
            [
                DataDeletionEvent(
                    request_id=request.id,
                    organization_id=request.organization_id,
                    action="executed",
                    actor_user_id=operator.id,
                    occurred_at=completed_at,
                ),
                DataDeletionEvent(
                    request_id=request.id,
                    organization_id=request.organization_id,
                    action="verified",
                    actor_user_id=operator.id,
                    occurred_at=completed_at,
                ),
                _operator_audit(request, operator.id, "succeeded", completed_at),
            ]
        )
        db.commit()
        db.refresh(receipt)
        return receipt
    except Exception:
        db.rollback()
        failed_request = db.get(DataDeletionRequest, request_id)
        if failed_request is not None:
            failed_at = _now()
            db.add(
                DataDeletionEvent(
                    request_id=failed_request.id,
                    organization_id=failed_request.organization_id,
                    action="failed",
                    actor_user_id=operator_user_id,
                    occurred_at=failed_at,
                )
            )
            db.add(_operator_audit(failed_request, operator_user_id, "error", failed_at))
            db.commit()
        raise


def verify_deletion_receipt(receipt: DataDeletionReceipt) -> bool:
    material = {
        "id": receipt.id,
        "request_id": receipt.request_id,
        "organization_id": receipt.organization_id,
        "scope_type": receipt.scope_type,
        "scope_id": receipt.scope_id,
        "deleted_counts": receipt.deleted_counts,
        "object_versions_deleted": receipt.object_versions_deleted,
        "delete_markers_deleted": receipt.delete_markers_deleted,
        "revoked_releases": receipt.revoked_releases,
        "backup_disposition": receipt.backup_disposition,
        "backup_expires_at": receipt.backup_expires_at,
        "approved_by_user_id": receipt.approved_by_user_id,
        "operator_user_id": receipt.operator_user_id,
        "completed_at": receipt.completed_at,
    }
    return receipt.receipt_sha256 == sha256_json(material)
