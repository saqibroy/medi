"""Append-only, data-minimized security audit ledger."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import SecurityAuditEvent, User
from ..observability import request_id_context


SAFE_DETAIL_KEYS = {
    "deidentification_profile_version",
    "deidentification_status",
    "export_format",
    "ingestion_status",
    "policy_version",
    "reason_code",
    "release_version",
    "slice_index",
    "source_format",
    "scope_type",
}


@dataclass(frozen=True)
class AuditRoute:
    action: str
    target_type: str | None = None
    target_parameter: str | None = None
    details: tuple[tuple[str, str | int], ...] = ()


AUDITED_ROUTES: dict[tuple[str, str], AuditRoute] = {
    ("POST", "/auth/login"): AuditRoute("auth.login"),
    ("POST", "/auth/logout"): AuditRoute("auth.logout"),
    ("GET", "/audit-events"): AuditRoute("audit.list", "organization"),
    ("POST", "/projects"): AuditRoute("project.create", "project"),
    ("PUT", "/projects/{project_id}"): AuditRoute("project.update", "project", "project_id"),
    ("GET", "/projects/{project_id}/releases"): AuditRoute("dataset_release.list", "project", "project_id"),
    ("POST", "/projects/{project_id}/releases"): AuditRoute("dataset_release.create", "dataset_release"),
    ("GET", "/dataset-releases/{release_id}"): AuditRoute("dataset_release.read", "dataset_release", "release_id"),
    ("POST", "/dataset-releases/{release_id}/revoke"): AuditRoute("dataset_release.revoke", "dataset_release", "release_id"),
    ("GET", "/governance/retention-policies"): AuditRoute("retention_policy.list", "organization"),
    ("POST", "/governance/retention-policies"): AuditRoute("retention_policy.create", "retention_policy"),
    ("GET", "/governance/legal-holds"): AuditRoute("legal_hold.list", "organization"),
    ("POST", "/governance/legal-holds"): AuditRoute("legal_hold.create", "legal_hold"),
    ("POST", "/governance/legal-holds/{hold_id}/release"): AuditRoute("legal_hold.release", "legal_hold", "hold_id"),
    ("GET", "/governance/deletion-requests"): AuditRoute("deletion_request.list", "organization"),
    ("POST", "/governance/deletion-requests"): AuditRoute("deletion_request.create", "deletion_request"),
    ("GET", "/governance/deletion-requests/{request_id}"): AuditRoute("deletion_request.read", "deletion_request", "request_id"),
    ("POST", "/governance/deletion-requests/{request_id}/approve"): AuditRoute("deletion_request.approve", "deletion_request", "request_id"),
    ("POST", "/governance/deletion-requests/{request_id}/cancel"): AuditRoute("deletion_request.cancel", "deletion_request", "request_id"),
    ("POST", "/projects/{project_id}/labels"): AuditRoute("label.create", "label"),
    ("PUT", "/labels/{label_id}"): AuditRoute("label.update", "label", "label_id"),
    ("DELETE", "/labels/{label_id}"): AuditRoute("label.delete", "label", "label_id"),
    ("POST", "/scans"): AuditRoute("scan.create", "scan"),
    ("POST", "/scans/upload"): AuditRoute("scan.upload", "scan"),
    ("POST", "/scans/{scan_id}/reprocess"): AuditRoute("scan.reprocess", "scan", "scan_id"),
    ("GET", "/scans/{scan_id}/slice/{slice_index}"): AuditRoute("scan.slice_read", "scan", "scan_id"),
    ("GET", "/scans/{scan_id}/slice/{slice_index}/metadata"): AuditRoute("scan.slice_metadata_read", "scan", "scan_id"),
    ("GET", "/scans/{scan_id}/slice/{slice_index}/url"): AuditRoute("scan.signed_url_issue", "scan", "scan_id"),
    ("POST", "/annotations"): AuditRoute("annotation.create", "annotation"),
    ("PUT", "/annotations/{annotation_id}"): AuditRoute("annotation.update", "annotation", "annotation_id"),
    ("PATCH", "/annotations/{annotation_id}/review"): AuditRoute("annotation.review", "annotation", "annotation_id"),
    ("DELETE", "/annotations/{annotation_id}"): AuditRoute("annotation.delete", "annotation", "annotation_id"),
    ("POST", "/annotations/{annotation_id}/mask"): AuditRoute("mask.upload", "annotation", "annotation_id"),
    ("GET", "/annotations/{annotation_id}/mask/{slice_index}"): AuditRoute("mask.read", "annotation", "annotation_id"),
    ("DELETE", "/annotations/{annotation_id}/mask/{slice_index}"): AuditRoute("mask.delete", "annotation", "annotation_id"),
}

for scope in ("projects", "scans"):
    target_parameter = "project_id" if scope == "projects" else "scan_id"
    target_type = "project" if scope == "projects" else "scan"
    base_path = "/projects/{project_id}" if scope == "projects" else "/scans/{scan_id}"
    for suffix, export_format in (
        ("/export", "native"),
        ("/export/coco", "coco"),
        ("/export/csv", "csv"),
        ("/export/yolo", "yolo"),
        ("/export/segmentation", "segmentation_manifest"),
    ):
        AUDITED_ROUTES[("GET", f"{base_path}{suffix}")] = AuditRoute(
            f"{target_type}.export",
            target_type,
            target_parameter,
            (("export_format", export_format),),
        )


def mark_request_actor(request: Request, user: User, session_id: UUID | None) -> None:
    """Attach only stable authorization identifiers to the request context."""

    request.state.audit_organization_id = user.organization_id
    request.state.audit_actor_user_id = user.id
    request.state.audit_actor_session_id = session_id


def mark_request_target(request: Request, target_id: UUID, **details: Any) -> None:
    """Attach a created target and explicitly safe outcome details."""

    request.state.audit_target_id = target_id
    request.state.audit_details = _sanitize_details(details)


def route_for_request(request: Request) -> AuditRoute | None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if not isinstance(route_path, str):
        # Exact literal paths remain auditable when an outer middleware (for
        # example the login limiter) returns before Starlette route matching.
        route_path = request.url.path
    return AUDITED_ROUTES.get((request.method.upper(), route_path))


def result_for_status(status_code: int) -> str:
    if status_code < 400:
        return "succeeded"
    if status_code in {401, 403}:
        return "denied"
    if status_code < 500:
        return "failed"
    return "error"


def create_event_for_request(
    db: Session,
    request: Request,
    route: AuditRoute,
    status_code: int,
    signing_key: str,
) -> SecurityAuditEvent:
    """Append one event from an allowlisted route without reading payload data."""

    target_id = getattr(request.state, "audit_target_id", None)
    if target_id is None and route.target_parameter is not None:
        raw_target = request.path_params.get(route.target_parameter)
        try:
            target_id = UUID(str(raw_target)) if raw_target is not None else None
        except ValueError:
            target_id = None
    if target_id is None and route.target_type == "organization":
        target_id = getattr(request.state, "audit_organization_id", None)

    path_details: dict[str, Any] = dict(route.details)
    if "slice_index" in request.path_params:
        try:
            path_details["slice_index"] = int(request.path_params["slice_index"])
        except (TypeError, ValueError):
            pass
    path_details.update(getattr(request.state, "audit_details", {}))

    event = SecurityAuditEvent(
        id=uuid4(),
        organization_id=getattr(request.state, "audit_organization_id", None),
        actor_user_id=getattr(request.state, "audit_actor_user_id", None),
        actor_session_id=getattr(request.state, "audit_actor_session_id", None),
        action=route.action,
        result=result_for_status(status_code),
        target_type=route.target_type,
        target_id=target_id,
        request_id=request_id_context.get(),
        details=_sanitize_details(path_details),
        occurred_at=datetime.now(timezone.utc),
        integrity_hash="",
    )
    event.integrity_hash = calculate_integrity_hash(event, signing_key)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def calculate_integrity_hash(event: SecurityAuditEvent, signing_key: str) -> str:
    canonical = json.dumps(
        {
            "action": event.action,
            "actor_session_id": _uuid_text(event.actor_session_id),
            "actor_user_id": _uuid_text(event.actor_user_id),
            "details": event.details,
            "id": str(event.id),
            "occurred_at": _utc_text(event.occurred_at),
            "organization_id": _uuid_text(event.organization_id),
            "request_id": event.request_id,
            "result": event.result,
            "target_id": _uuid_text(event.target_id),
            "target_type": event.target_type,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hmac.new(signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_integrity(event: SecurityAuditEvent, signing_key: str) -> bool:
    return hmac.compare_digest(event.integrity_hash, calculate_integrity_hash(event, signing_key))


def list_events(
    db: Session,
    current_user: User,
    *,
    action: str | None,
    result: str | None,
    limit: int,
    offset: int,
) -> list[SecurityAuditEvent]:
    statement: Select[tuple[SecurityAuditEvent]] = select(SecurityAuditEvent).where(
        SecurityAuditEvent.organization_id == current_user.organization_id
    )
    if action is not None:
        statement = statement.where(SecurityAuditEvent.action == action)
    if result is not None:
        statement = statement.where(SecurityAuditEvent.result == result)
    statement = statement.order_by(SecurityAuditEvent.occurred_at.desc(), SecurityAuditEvent.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(statement))


def _sanitize_details(details: dict[str, Any]) -> dict[str, str | int | bool | None]:
    sanitized: dict[str, str | int | bool | None] = {}
    for key, value in details.items():
        if key not in SAFE_DETAIL_KEYS:
            raise ValueError(f"unsupported audit detail key: {key}")
        if value is None or isinstance(value, (bool, int)):
            sanitized[key] = value
        elif isinstance(value, str):
            sanitized[key] = value[:100]
        else:
            raise ValueError(f"unsupported audit detail value for: {key}")
    return sanitized


def _uuid_text(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _utc_text(value: datetime) -> str:
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.isoformat()
