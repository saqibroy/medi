"""Data-minimized processing evidence and privacy-request workflow controls."""

from __future__ import annotations

import calendar
import hashlib
import hmac
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    DataDeletionRequest,
    DataRetentionPolicy,
    Organization,
    PrivacyProcessingRecord,
    PrivacyProcessingRecordEvent,
    PrivacyRequest,
    PrivacyRequestEvent,
    Project,
    Scan,
    User,
)
from ..settings import get_settings
from . import data_lifecycle_service


TERMINAL_REQUEST_ACTIONS = {"fulfilled", "denied", "cancelled"}
EXPECTED_OUTCOMES = {
    "access": "secure_delivery",
    "rectification": "record_corrected",
    "restriction": "processing_restricted",
    "objection": "objection_applied",
    "portability": "secure_delivery",
    "erasure": "erasure_verified",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _event_groups(events: Iterable[Any], key_name: str) -> dict[UUID, list[Any]]:
    grouped: dict[UUID, list[Any]] = defaultdict(list)
    for event in events:
        grouped[getattr(event, key_name)].append(event)
    return grouped


def _processing_events(
    db: Session, record_ids: Iterable[UUID]
) -> dict[UUID, list[PrivacyProcessingRecordEvent]]:
    ids = list(record_ids)
    if not ids:
        return defaultdict(list)
    return _event_groups(
        db.scalars(
            select(PrivacyProcessingRecordEvent)
            .where(PrivacyProcessingRecordEvent.processing_record_id.in_(ids))
            .order_by(PrivacyProcessingRecordEvent.occurred_at, PrivacyProcessingRecordEvent.id)
        ),
        "processing_record_id",
    )


def processing_record_status(
    record: PrivacyProcessingRecord,
    events: Iterable[PrivacyProcessingRecordEvent],
    latest_version: int,
) -> str:
    actions = {event.action for event in events}
    if "revoked" in actions:
        return "revoked"
    if "recorded" not in actions:
        return "unrecorded"
    if record.version < latest_version:
        return "superseded"
    if record.dpia_outcome == "consultation_required":
        return "consultation_required"
    return "active"


def _processing_response(
    record: PrivacyProcessingRecord,
    events: list[PrivacyProcessingRecordEvent],
    latest_version: int,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "organization_id": record.organization_id,
        "activity_key": record.activity_key,
        "version": record.version,
        "organization_role": record.organization_role,
        "purpose_code": record.purpose_code,
        "lawful_basis": record.lawful_basis,
        "health_data_processed": record.health_data_processed,
        "article9_condition": record.article9_condition,
        "data_subject_categories": record.data_subject_categories,
        "personal_data_categories": record.personal_data_categories,
        "recipient_categories": record.recipient_categories,
        "processor_references": record.processor_references,
        "processing_locations": record.processing_locations,
        "transfer_mechanism": record.transfer_mechanism,
        "transfer_safeguard_reference": record.transfer_safeguard_reference,
        "retention_policy_id": record.retention_policy_id,
        "retention_policy_version": record.retention_policy_version,
        "security_measure_references": record.security_measure_references,
        "dpia_required": record.dpia_required,
        "dpia_outcome": record.dpia_outcome,
        "dpia_reference": record.dpia_reference,
        "dpo_review_reference": record.dpo_review_reference,
        "approval_reference": record.approval_reference,
        "created_by_user_id": record.created_by_user_id,
        "created_at": record.created_at,
        "status": processing_record_status(record, events, latest_version),
        "events": events,
    }


def create_processing_record(db: Session, payload: Any, current_user: User) -> dict[str, Any]:
    organization = db.scalar(
        select(Organization).where(Organization.id == current_user.organization_id).with_for_update()
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    policy = db.get(DataRetentionPolicy, payload.retention_policy_id)
    if policy is None or policy.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retention policy not found")
    previous_version = db.scalar(
        select(func.max(PrivacyProcessingRecord.version)).where(
            PrivacyProcessingRecord.organization_id == current_user.organization_id,
            PrivacyProcessingRecord.activity_key == payload.activity_key,
        )
    )
    occurred_at = _now()
    values = payload.model_dump()
    values.pop("retention_policy_id")
    record = PrivacyProcessingRecord(
        organization_id=current_user.organization_id,
        activity_key=payload.activity_key,
        version=(previous_version or 0) + 1,
        retention_policy_id=policy.id,
        retention_policy_version=policy.version,
        created_by_user_id=current_user.id,
        created_at=occurred_at,
        **{key: value for key, value in values.items() if key != "activity_key"},
    )
    db.add(record)
    db.flush()
    event = PrivacyProcessingRecordEvent(
        processing_record_id=record.id,
        organization_id=record.organization_id,
        action="recorded",
        actor_user_id=current_user.id,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(record)
    return _processing_response(record, [event], record.version)


def list_processing_records(db: Session, current_user: User) -> list[dict[str, Any]]:
    records = list(
        db.scalars(
            select(PrivacyProcessingRecord)
            .where(PrivacyProcessingRecord.organization_id == current_user.organization_id)
            .order_by(
                PrivacyProcessingRecord.activity_key,
                PrivacyProcessingRecord.version.desc(),
                PrivacyProcessingRecord.id,
            )
        )
    )
    events = _processing_events(db, [record.id for record in records])
    latest_versions: dict[str, int] = {}
    for record in records:
        latest_versions[record.activity_key] = max(latest_versions.get(record.activity_key, 0), record.version)
    return [_processing_response(record, events[record.id], latest_versions[record.activity_key]) for record in records]


def revoke_processing_record(db: Session, record_id: UUID, current_user: User) -> dict[str, Any]:
    record = db.get(PrivacyProcessingRecord, record_id)
    if record is None or record.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Privacy processing record not found")
    events = _processing_events(db, [record.id])[record.id]
    if "revoked" in {event.action for event in events}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Privacy processing record is already revoked")
    if record.created_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A different administrator must revoke the record")
    event = PrivacyProcessingRecordEvent(
        processing_record_id=record.id,
        organization_id=record.organization_id,
        action="revoked",
        actor_user_id=current_user.id,
        occurred_at=_now(),
    )
    db.add(event)
    db.commit()
    latest_version = db.scalar(
        select(func.max(PrivacyProcessingRecord.version)).where(
            PrivacyProcessingRecord.organization_id == record.organization_id,
            PrivacyProcessingRecord.activity_key == record.activity_key,
        )
    )
    return _processing_response(record, [*events, event], latest_version or record.version)


def _scope_exists(db: Session, organization_id: UUID, scope_type: str, scope_id: UUID) -> None:
    exists = False
    if scope_type == "organization":
        exists = scope_id == organization_id and db.get(Organization, organization_id) is not None
    elif scope_type == "project":
        exists = db.scalar(
            select(Project.id).where(Project.id == scope_id, Project.organization_id == organization_id)
        ) is not None
    elif scope_type == "scan":
        exists = db.scalar(
            select(Scan.id)
            .join(Project, Scan.project_id == Project.id)
            .where(Scan.id == scope_id, Project.organization_id == organization_id)
        ) is not None
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Privacy request scope not found")


def _subject_digest(organization_id: UUID, external_subject_reference: str) -> str:
    key = get_settings().privacy_reference_key.encode("utf-8")
    message = f"privacy-subject:{organization_id}:{external_subject_reference.strip()}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _request_events(db: Session, request_ids: Iterable[UUID]) -> dict[UUID, list[PrivacyRequestEvent]]:
    ids = list(request_ids)
    if not ids:
        return defaultdict(list)
    return _event_groups(
        db.scalars(
            select(PrivacyRequestEvent)
            .where(PrivacyRequestEvent.privacy_request_id.in_(ids))
            .order_by(PrivacyRequestEvent.occurred_at, PrivacyRequestEvent.id)
        ),
        "privacy_request_id",
    )


def privacy_request_status(events: Iterable[PrivacyRequestEvent]) -> str:
    actions = [event.action for event in events]
    for terminal in ("fulfilled", "denied", "cancelled"):
        if terminal in actions:
            return terminal
    for active in ("accepted", "identity_verified", "received"):
        if active in actions:
            return active
    return "untracked"


def _effective_due_at(request: PrivacyRequest, events: Iterable[PrivacyRequestEvent]) -> datetime:
    extensions = [event.new_due_at for event in events if event.action == "deadline_extended" and event.new_due_at is not None]
    return max([request.response_due_at, *extensions], key=_aware)


def _deadline_status(request: PrivacyRequest, events: list[PrivacyRequestEvent]) -> str:
    due_at = _aware(_effective_due_at(request, events))
    terminal_events = [event for event in events if event.action in TERMINAL_REQUEST_ACTIONS]
    if terminal_events:
        completed_at = _aware(terminal_events[-1].occurred_at)
        return "completed_on_time" if completed_at <= due_at else "completed_late"
    return "on_time" if _now() <= due_at else "overdue"


def _request_response(request: PrivacyRequest, events: list[PrivacyRequestEvent]) -> dict[str, Any]:
    return {
        "id": request.id,
        "organization_id": request.organization_id,
        "case_reference": request.case_reference,
        "subject_reference_token": f"sha256:{request.subject_reference_digest[:12]}",
        "request_type": request.request_type,
        "scope_type": request.scope_type,
        "scope_id": request.scope_id,
        "received_at": request.received_at,
        "response_due_at": request.response_due_at,
        "effective_due_at": _effective_due_at(request, events),
        "created_by_user_id": request.created_by_user_id,
        "created_at": request.created_at,
        "status": privacy_request_status(events),
        "deadline_status": _deadline_status(request, events),
        "events": events,
    }


def create_privacy_request(db: Session, payload: Any, current_user: User) -> dict[str, Any]:
    _scope_exists(db, current_user.organization_id, payload.scope_type, payload.scope_id)
    if db.scalar(
        select(PrivacyRequest.id).where(
            PrivacyRequest.organization_id == current_user.organization_id,
            PrivacyRequest.case_reference == payload.case_reference,
        )
    ) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Privacy case reference already exists")
    occurred_at = _now()
    request = PrivacyRequest(
        organization_id=current_user.organization_id,
        case_reference=payload.case_reference,
        subject_reference_digest=_subject_digest(current_user.organization_id, payload.external_subject_reference),
        request_type=payload.request_type,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        received_at=occurred_at,
        response_due_at=_add_calendar_months(occurred_at, 1),
        created_by_user_id=current_user.id,
        created_at=occurred_at,
    )
    db.add(request)
    db.flush()
    event = PrivacyRequestEvent(
        privacy_request_id=request.id,
        organization_id=request.organization_id,
        action="received",
        actor_user_id=current_user.id,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(request)
    return _request_response(request, [event])


def list_privacy_requests(db: Session, current_user: User) -> list[dict[str, Any]]:
    requests = list(
        db.scalars(
            select(PrivacyRequest)
            .where(PrivacyRequest.organization_id == current_user.organization_id)
            .order_by(PrivacyRequest.created_at.desc(), PrivacyRequest.id.desc())
        )
    )
    events = _request_events(db, [request.id for request in requests])
    return [_request_response(request, events[request.id]) for request in requests]


def get_privacy_request(db: Session, request_id: UUID, current_user: User) -> dict[str, Any]:
    request = db.get(PrivacyRequest, request_id)
    if request is None or request.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Privacy request not found")
    return _request_response(request, _request_events(db, [request.id])[request.id])


def verify_identity(db: Session, request_id: UUID, payload: Any, current_user: User) -> dict[str, Any]:
    request = _request_for_event(db, request_id, current_user)
    events = _request_events(db, [request.id])[request.id]
    if privacy_request_status(events) != "received":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Privacy request is not awaiting identity verification")
    if request.created_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A different administrator must verify identity")
    event = _append_request_event(
        db,
        request,
        current_user,
        action="identity_verified",
        evidence_reference=payload.evidence_reference,
    )
    return _request_response(request, [*events, event])


def accept_privacy_request(db: Session, request_id: UUID, payload: Any, current_user: User) -> dict[str, Any]:
    request = _request_for_event(db, request_id, current_user)
    events = _request_events(db, [request.id])[request.id]
    if privacy_request_status(events) != "identity_verified":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Verified identity is required before acceptance")
    linked_id = payload.linked_deletion_request_id
    if request.request_type == "erasure":
        if linked_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Erasure acceptance requires a deletion request")
        _validate_deletion_link(db, request, linked_id, current_user)
    elif linked_id is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Deletion requests may only be linked to erasure")
    event = _append_request_event(
        db,
        request,
        current_user,
        action="accepted",
        evidence_reference=payload.evidence_reference,
        linked_deletion_request_id=linked_id,
    )
    return _request_response(request, [*events, event])


def fulfill_privacy_request(db: Session, request_id: UUID, payload: Any, current_user: User) -> dict[str, Any]:
    request = _request_for_event(db, request_id, current_user)
    events = _request_events(db, [request.id])[request.id]
    if privacy_request_status(events) != "accepted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Privacy request must be accepted before fulfillment")
    if payload.outcome_code != EXPECTED_OUTCOMES[request.request_type]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Outcome does not match privacy request type")
    linked_id = next(
        (event.linked_deletion_request_id for event in reversed(events) if event.action == "accepted"),
        None,
    )
    if request.request_type == "erasure":
        if linked_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Erasure request has no governed deletion link")
        deletion = _validate_deletion_link(db, request, linked_id, current_user)
        if deletion["status"] not in {"executed", "verified"} or deletion["receipt"] is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Erasure requires an executed deletion receipt")
    event = _append_request_event(
        db,
        request,
        current_user,
        action="fulfilled",
        outcome_code=payload.outcome_code,
        evidence_reference=payload.evidence_reference,
        linked_deletion_request_id=linked_id,
    )
    return _request_response(request, [*events, event])


def deny_privacy_request(db: Session, request_id: UUID, payload: Any, current_user: User) -> dict[str, Any]:
    request = _request_for_event(db, request_id, current_user)
    events = _request_events(db, [request.id])[request.id]
    current_status = privacy_request_status(events)
    if current_status not in {"received", "identity_verified"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Privacy request cannot be denied in its current state")
    if request.created_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A different administrator must deny the request")
    if current_status == "received" and payload.reason_code != "identity_not_verified":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Substantive denial requires verified identity")
    if current_status == "identity_verified" and payload.reason_code == "identity_not_verified":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Verified identity cannot use this denial reason")
    event = _append_request_event(
        db,
        request,
        current_user,
        action="denied",
        reason_code=payload.reason_code,
        evidence_reference=payload.evidence_reference,
    )
    return _request_response(request, [*events, event])


def cancel_privacy_request(db: Session, request_id: UUID, payload: Any, current_user: User) -> dict[str, Any]:
    request = _request_for_event(db, request_id, current_user)
    events = _request_events(db, [request.id])[request.id]
    if privacy_request_status(events) in TERMINAL_REQUEST_ACTIONS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Privacy request is already closed")
    event = _append_request_event(
        db,
        request,
        current_user,
        action="cancelled",
        reason_code=payload.reason_code,
        evidence_reference=payload.evidence_reference,
    )
    return _request_response(request, [*events, event])


def extend_privacy_request(db: Session, request_id: UUID, payload: Any, current_user: User) -> dict[str, Any]:
    request = _request_for_event(db, request_id, current_user)
    events = _request_events(db, [request.id])[request.id]
    if privacy_request_status(events) in TERMINAL_REQUEST_ACTIONS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed privacy request cannot be extended")
    if any(event.action == "deadline_extended" for event in events):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Privacy request deadline has already been extended")
    new_due_at = _add_calendar_months(_aware(request.response_due_at), 2)
    event = _append_request_event(
        db,
        request,
        current_user,
        action="deadline_extended",
        reason_code=payload.reason_code,
        evidence_reference=payload.evidence_reference,
        new_due_at=new_due_at,
    )
    return _request_response(request, [*events, event])


def _request_for_event(db: Session, request_id: UUID, current_user: User) -> PrivacyRequest:
    request = db.get(PrivacyRequest, request_id)
    if request is None or request.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Privacy request not found")
    return request


def _append_request_event(
    db: Session,
    request: PrivacyRequest,
    current_user: User,
    *,
    action: str,
    reason_code: str | None = None,
    outcome_code: str | None = None,
    evidence_reference: str | None = None,
    linked_deletion_request_id: UUID | None = None,
    new_due_at: datetime | None = None,
) -> PrivacyRequestEvent:
    event = PrivacyRequestEvent(
        privacy_request_id=request.id,
        organization_id=request.organization_id,
        action=action,
        actor_user_id=current_user.id,
        reason_code=reason_code,
        outcome_code=outcome_code,
        evidence_reference=evidence_reference,
        linked_deletion_request_id=linked_deletion_request_id,
        new_due_at=new_due_at,
        occurred_at=_now(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _validate_deletion_link(
    db: Session,
    request: PrivacyRequest,
    deletion_request_id: UUID,
    current_user: User,
) -> dict[str, Any]:
    deletion = db.get(DataDeletionRequest, deletion_request_id)
    if deletion is None or deletion.organization_id != request.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Governed deletion request not found")
    if (
        deletion.reason_code != "erasure_request"
        or deletion.scope_type != request.scope_type
        or deletion.scope_id != request.scope_id
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Deletion request does not match the erasure scope")
    return data_lifecycle_service.get_deletion_request(db, deletion.id, current_user)
