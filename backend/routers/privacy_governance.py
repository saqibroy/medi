"""Administrator-only processing evidence and privacy-request workflow APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import (
    PrivacyIdentityVerificationCreate,
    PrivacyProcessingRecordCreate,
    PrivacyProcessingRecordRead,
    PrivacyRequestAcceptCreate,
    PrivacyRequestCancelCreate,
    PrivacyRequestCreate,
    PrivacyRequestDenyCreate,
    PrivacyRequestExtendCreate,
    PrivacyRequestFulfillCreate,
    PrivacyRequestRead,
)
from ..security import require_admin
from ..services import privacy_governance_service
from ..services.audit_service import mark_request_target


router = APIRouter(prefix="/governance/privacy", tags=["privacy-governance"])


@router.get("/processing-records", response_model=list[PrivacyProcessingRecordRead])
async def list_processing_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[PrivacyProcessingRecordRead]:
    return privacy_governance_service.list_processing_records(db, current_user)


@router.post("/processing-records", response_model=PrivacyProcessingRecordRead, status_code=201)
async def create_processing_record(
    request: Request,
    payload: PrivacyProcessingRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyProcessingRecordRead:
    record = privacy_governance_service.create_processing_record(db, payload, current_user)
    mark_request_target(
        request,
        record["id"],
        policy_version=record["retention_policy_version"],
        purpose_code=record["purpose_code"],
        workflow_status=record["status"],
    )
    return record


@router.post("/processing-records/{record_id}/revoke", response_model=PrivacyProcessingRecordRead)
async def revoke_processing_record(
    request: Request,
    record_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyProcessingRecordRead:
    record = privacy_governance_service.revoke_processing_record(db, record_id, current_user)
    mark_request_target(request, record["id"], purpose_code=record["purpose_code"], workflow_status=record["status"])
    return record


@router.get("/requests", response_model=list[PrivacyRequestRead])
async def list_privacy_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[PrivacyRequestRead]:
    return privacy_governance_service.list_privacy_requests(db, current_user)


@router.post("/requests", response_model=PrivacyRequestRead, status_code=201)
async def create_privacy_request(
    request: Request,
    payload: PrivacyRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    privacy_request = privacy_governance_service.create_privacy_request(db, payload, current_user)
    _mark_privacy_request(request, privacy_request)
    return privacy_request


@router.get("/requests/{request_id}", response_model=PrivacyRequestRead)
async def get_privacy_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    return privacy_governance_service.get_privacy_request(db, request_id, current_user)


@router.post("/requests/{request_id}/verify-identity", response_model=PrivacyRequestRead)
async def verify_privacy_request_identity(
    request: Request,
    request_id: UUID,
    payload: PrivacyIdentityVerificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    privacy_request = privacy_governance_service.verify_identity(db, request_id, payload, current_user)
    _mark_privacy_request(request, privacy_request)
    return privacy_request


@router.post("/requests/{request_id}/accept", response_model=PrivacyRequestRead)
async def accept_privacy_request(
    request: Request,
    request_id: UUID,
    payload: PrivacyRequestAcceptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    privacy_request = privacy_governance_service.accept_privacy_request(db, request_id, payload, current_user)
    _mark_privacy_request(request, privacy_request)
    return privacy_request


@router.post("/requests/{request_id}/fulfill", response_model=PrivacyRequestRead)
async def fulfill_privacy_request(
    request: Request,
    request_id: UUID,
    payload: PrivacyRequestFulfillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    privacy_request = privacy_governance_service.fulfill_privacy_request(db, request_id, payload, current_user)
    _mark_privacy_request(request, privacy_request)
    return privacy_request


@router.post("/requests/{request_id}/deny", response_model=PrivacyRequestRead)
async def deny_privacy_request(
    request: Request,
    request_id: UUID,
    payload: PrivacyRequestDenyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    privacy_request = privacy_governance_service.deny_privacy_request(db, request_id, payload, current_user)
    _mark_privacy_request(request, privacy_request, reason_code=payload.reason_code)
    return privacy_request


@router.post("/requests/{request_id}/cancel", response_model=PrivacyRequestRead)
async def cancel_privacy_request(
    request: Request,
    request_id: UUID,
    payload: PrivacyRequestCancelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    privacy_request = privacy_governance_service.cancel_privacy_request(db, request_id, payload, current_user)
    _mark_privacy_request(request, privacy_request, reason_code=payload.reason_code)
    return privacy_request


@router.post("/requests/{request_id}/extend", response_model=PrivacyRequestRead)
async def extend_privacy_request(
    request: Request,
    request_id: UUID,
    payload: PrivacyRequestExtendCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> PrivacyRequestRead:
    privacy_request = privacy_governance_service.extend_privacy_request(db, request_id, payload, current_user)
    _mark_privacy_request(request, privacy_request, reason_code=payload.reason_code)
    return privacy_request


def _mark_privacy_request(request: Request, privacy_request: dict, **details: str) -> None:
    mark_request_target(
        request,
        privacy_request["id"],
        scope_type=privacy_request["scope_type"],
        request_type=privacy_request["request_type"],
        workflow_status=privacy_request["status"],
        **details,
    )
