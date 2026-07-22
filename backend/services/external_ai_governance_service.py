"""Deny-by-default external AI provider, data-flow, and egress authorization controls."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    ExternalAIDataFlowApproval,
    ExternalAIDataFlowEvent,
    ExternalAIEgressDecision,
    ExternalAIProviderApproval,
    ExternalAIProviderEvent,
    Organization,
    Project,
    Scan,
    User,
)
from ..settings import get_settings


PROHIBITED_DATA_CLASSES = ("direct_identifiers", "free_text_clinical_notes", "raw_dicom", "raw_dicom_metadata")
SCAN_DATA_CLASSES = {"deidentified_pixels", "derived_previews", "deidentified_metadata", "annotation_geometry"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _event_groups(events: Iterable[Any], key_name: str) -> dict[UUID, list[Any]]:
    grouped: dict[UUID, list[Any]] = defaultdict(list)
    for event in events:
        grouped[getattr(event, key_name)].append(event)
    return grouped


def _provider_events(db: Session, provider_ids: Iterable[UUID]) -> dict[UUID, list[ExternalAIProviderEvent]]:
    ids = list(provider_ids)
    if not ids:
        return defaultdict(list)
    return _event_groups(
        db.scalars(
            select(ExternalAIProviderEvent)
            .where(ExternalAIProviderEvent.provider_approval_id.in_(ids))
            .order_by(ExternalAIProviderEvent.occurred_at, ExternalAIProviderEvent.id)
        ),
        "provider_approval_id",
    )


def provider_status(events: Iterable[ExternalAIProviderEvent]) -> str:
    actions = {event.action for event in events}
    if "revoked" in actions:
        return "revoked"
    return "active" if "approved" in actions else "unapproved"


def _provider_response(provider: ExternalAIProviderApproval, events: list[ExternalAIProviderEvent]) -> dict[str, Any]:
    return {
        "id": provider.id,
        "organization_id": provider.organization_id,
        "provider_key": provider.provider_key,
        "version": provider.version,
        "display_name": provider.display_name,
        "model_name": provider.model_name,
        "model_version": provider.model_version,
        "purpose_code": provider.purpose_code,
        "endpoint_origin": provider.endpoint_origin,
        "region_code": provider.region_code,
        "data_classes": provider.data_classes,
        "retention_days": provider.retention_days,
        "training_use_allowed": provider.training_use_allowed,
        "subprocessors": provider.subprocessors,
        "transfer_mechanism": provider.transfer_mechanism,
        "contract_owner_reference": provider.contract_owner_reference,
        "approval_reference": provider.approval_reference,
        "created_by_user_id": provider.created_by_user_id,
        "created_at": provider.created_at,
        "status": provider_status(events),
        "events": events,
    }


def create_provider(db: Session, payload: Any, current_user: User) -> dict[str, Any]:
    organization = db.scalar(
        select(Organization).where(Organization.id == current_user.organization_id).with_for_update()
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    previous_version = db.scalar(
        select(func.max(ExternalAIProviderApproval.version)).where(
            ExternalAIProviderApproval.organization_id == current_user.organization_id,
            ExternalAIProviderApproval.provider_key == payload.provider_key,
        )
    )
    occurred_at = _now()
    provider = ExternalAIProviderApproval(
        organization_id=current_user.organization_id,
        version=(previous_version or 0) + 1,
        created_by_user_id=current_user.id,
        created_at=occurred_at,
        **payload.model_dump(),
    )
    db.add(provider)
    db.flush()
    event = ExternalAIProviderEvent(
        provider_approval_id=provider.id,
        organization_id=provider.organization_id,
        action="approved",
        actor_user_id=current_user.id,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(provider)
    return _provider_response(provider, [event])


def list_providers(db: Session, current_user: User) -> list[dict[str, Any]]:
    providers = list(
        db.scalars(
            select(ExternalAIProviderApproval)
            .where(ExternalAIProviderApproval.organization_id == current_user.organization_id)
            .order_by(
                ExternalAIProviderApproval.provider_key,
                ExternalAIProviderApproval.version.desc(),
                ExternalAIProviderApproval.id,
            )
        )
    )
    events = _provider_events(db, [provider.id for provider in providers])
    return [_provider_response(provider, events[provider.id]) for provider in providers]


def revoke_provider(db: Session, provider_id: UUID, current_user: User) -> dict[str, Any]:
    provider = db.get(ExternalAIProviderApproval, provider_id)
    if provider is None or provider.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External AI provider approval not found")
    events = _provider_events(db, [provider.id])[provider.id]
    if provider_status(events) == "revoked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="External AI provider approval is already revoked")
    if provider.created_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A different administrator must revoke provider approval")
    event = ExternalAIProviderEvent(
        provider_approval_id=provider.id,
        organization_id=provider.organization_id,
        action="revoked",
        actor_user_id=current_user.id,
        occurred_at=_now(),
    )
    db.add(event)
    db.commit()
    return _provider_response(provider, [*events, event])


def _flow_events(db: Session, flow_ids: Iterable[UUID]) -> dict[UUID, list[ExternalAIDataFlowEvent]]:
    ids = list(flow_ids)
    if not ids:
        return defaultdict(list)
    return _event_groups(
        db.scalars(
            select(ExternalAIDataFlowEvent)
            .where(ExternalAIDataFlowEvent.data_flow_id.in_(ids))
            .order_by(ExternalAIDataFlowEvent.occurred_at, ExternalAIDataFlowEvent.id)
        ),
        "data_flow_id",
    )


def flow_status(flow: ExternalAIDataFlowApproval, events: Iterable[ExternalAIDataFlowEvent]) -> str:
    actions = {event.action for event in events}
    if "revoked" in actions:
        return "revoked"
    if "approved" not in actions:
        return "unapproved"
    if flow.expires_at is not None and _aware(flow.expires_at) <= _now():
        return "expired"
    return "active"


def _flow_response(flow: ExternalAIDataFlowApproval, events: list[ExternalAIDataFlowEvent]) -> dict[str, Any]:
    return {
        "id": flow.id,
        "organization_id": flow.organization_id,
        "project_id": flow.project_id,
        "provider_approval_id": flow.provider_approval_id,
        "purpose_code": flow.purpose_code,
        "data_classes": flow.data_classes,
        "approval_reference": flow.approval_reference,
        "expires_at": flow.expires_at,
        "created_by_user_id": flow.created_by_user_id,
        "created_at": flow.created_at,
        "status": flow_status(flow, events),
        "events": events,
    }


def create_data_flow(db: Session, payload: Any, current_user: User) -> dict[str, Any]:
    project = db.scalar(
        select(Project).where(
            Project.id == payload.project_id,
            Project.organization_id == current_user.organization_id,
            Project.lifecycle_status == "active",
        )
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    provider = db.get(ExternalAIProviderApproval, payload.provider_approval_id)
    if provider is None or provider.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External AI provider approval not found")
    provider_events = _provider_events(db, [provider.id])[provider.id]
    if provider_status(provider_events) != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="External AI provider approval is revoked")
    if payload.purpose_code != provider.purpose_code:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Data-flow purpose is not approved by the provider policy")
    if not set(payload.data_classes).issubset(set(provider.data_classes)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Data flow contains a data class not approved by the provider policy")
    if payload.expires_at is not None and _aware(payload.expires_at) <= _now():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Data-flow expiry must be in the future")
    existing = list(
        db.scalars(
            select(ExternalAIDataFlowApproval).where(
                ExternalAIDataFlowApproval.organization_id == current_user.organization_id,
                ExternalAIDataFlowApproval.project_id == project.id,
                ExternalAIDataFlowApproval.provider_approval_id == provider.id,
                ExternalAIDataFlowApproval.purpose_code == payload.purpose_code,
            )
        )
    )
    existing_events = _flow_events(db, [flow.id for flow in existing])
    if any(flow_status(flow, existing_events[flow.id]) == "active" for flow in existing):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active external AI data flow already covers this project and provider")
    occurred_at = _now()
    flow = ExternalAIDataFlowApproval(
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        created_at=occurred_at,
        **payload.model_dump(),
    )
    db.add(flow)
    db.flush()
    event = ExternalAIDataFlowEvent(
        data_flow_id=flow.id,
        organization_id=flow.organization_id,
        action="approved",
        actor_user_id=current_user.id,
        occurred_at=occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(flow)
    return _flow_response(flow, [event])


def list_data_flows(db: Session, current_user: User) -> list[dict[str, Any]]:
    flows = list(
        db.scalars(
            select(ExternalAIDataFlowApproval)
            .where(ExternalAIDataFlowApproval.organization_id == current_user.organization_id)
            .order_by(ExternalAIDataFlowApproval.created_at.desc(), ExternalAIDataFlowApproval.id.desc())
        )
    )
    events = _flow_events(db, [flow.id for flow in flows])
    return [_flow_response(flow, events[flow.id]) for flow in flows]


def revoke_data_flow(db: Session, flow_id: UUID, current_user: User) -> dict[str, Any]:
    flow = db.get(ExternalAIDataFlowApproval, flow_id)
    if flow is None or flow.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External AI data flow not found")
    events = _flow_events(db, [flow.id])[flow.id]
    if flow_status(flow, events) != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="External AI data flow is not active")
    if flow.created_by_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A different administrator must revoke the data flow")
    event = ExternalAIDataFlowEvent(
        data_flow_id=flow.id,
        organization_id=flow.organization_id,
        action="revoked",
        actor_user_id=current_user.id,
        occurred_at=_now(),
    )
    db.add(event)
    db.commit()
    return _flow_response(flow, [*events, event])


def _dataset_is_deidentified(db: Session, project_id: UUID, requested_data_classes: Iterable[str]) -> bool:
    if not set(requested_data_classes).intersection(SCAN_DATA_CLASSES):
        return True
    scans = list(db.scalars(select(Scan).where(Scan.project_id == project_id)))
    if not scans:
        return False
    return all(
        scan.source_format == "synthetic"
        or (scan.ingestion_status == "ready" and scan.deidentification_status == "passed")
        for scan in scans
    )


def evaluate_egress(db: Session, payload: Any, current_user: User) -> ExternalAIEgressDecision:
    """Evaluate and persist authorization evidence without making any provider call."""

    flow = db.get(ExternalAIDataFlowApproval, payload.data_flow_id)
    if flow is None or flow.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External AI data flow not found")
    provider = db.get(ExternalAIProviderApproval, flow.provider_approval_id)
    if provider is None or provider.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="External AI provider policy is unavailable")
    project = db.get(Project, flow.project_id)
    settings = get_settings()
    provider_events = _provider_events(db, [provider.id])[provider.id]
    flow_events = _flow_events(db, [flow.id])[flow.id]

    reason = "authorized"
    current_provider_status = provider_status(provider_events)
    current_flow_status = flow_status(flow, flow_events)
    if not settings.external_ai_enabled:
        reason = "feature_disabled"
    elif current_provider_status == "revoked":
        reason = "provider_revoked"
    elif current_provider_status != "active":
        reason = "provider_unapproved"
    elif current_flow_status == "revoked":
        reason = "flow_revoked"
    elif current_flow_status == "unapproved":
        reason = "flow_unapproved"
    elif current_flow_status == "expired":
        reason = "flow_expired"
    elif provider.endpoint_origin not in settings.external_ai_allowed_origins:
        reason = "origin_not_allowlisted"
    elif project is None or project.organization_id != current_user.organization_id or project.lifecycle_status != "active":
        reason = "project_unavailable"
    elif payload.purpose_code != flow.purpose_code or payload.purpose_code != provider.purpose_code:
        reason = "purpose_not_approved"
    elif not set(payload.requested_data_classes).issubset(set(flow.data_classes)) or not set(
        payload.requested_data_classes
    ).issubset(set(provider.data_classes)):
        reason = "data_class_not_approved"
    elif not _dataset_is_deidentified(db, flow.project_id, payload.requested_data_classes):
        reason = "dataset_not_deidentified"

    decision = ExternalAIEgressDecision(
        organization_id=current_user.organization_id,
        provider_approval_id=provider.id,
        data_flow_id=flow.id,
        project_id=flow.project_id,
        actor_user_id=current_user.id,
        purpose_code=payload.purpose_code,
        requested_data_classes=payload.requested_data_classes,
        result="allowed" if reason == "authorized" else "denied",
        reason_code=reason,
        occurred_at=_now(),
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def list_decisions(db: Session, current_user: User, limit: int = 100) -> list[ExternalAIEgressDecision]:
    return list(
        db.scalars(
            select(ExternalAIEgressDecision)
            .where(ExternalAIEgressDecision.organization_id == current_user.organization_id)
            .order_by(ExternalAIEgressDecision.occurred_at.desc(), ExternalAIEgressDecision.id.desc())
            .limit(limit)
        )
    )


def external_ai_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": settings.external_ai_enabled,
        "allowed_origins": list(settings.external_ai_allowed_origins),
        "provider_network_call_implemented": False,
        "permanently_prohibited_data_classes": list(PROHIBITED_DATA_CLASSES),
    }
