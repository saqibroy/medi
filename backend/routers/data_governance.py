"""Administrator-only retention, legal-hold, and deletion approval APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import (
    DataDeletionRequestCreate,
    DataDeletionRequestRead,
    DataRetentionPolicyCreate,
    DataRetentionPolicyRead,
    LegalHoldCreate,
    LegalHoldRead,
)
from ..security import require_admin
from ..services import data_lifecycle_service
from ..services.audit_service import mark_request_target


router = APIRouter(prefix="/governance", tags=["data-governance"])


@router.get("/retention-policies", response_model=list[DataRetentionPolicyRead])
async def list_retention_policies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[DataRetentionPolicyRead]:
    return data_lifecycle_service.list_retention_policies(db, current_user)


@router.post("/retention-policies", response_model=DataRetentionPolicyRead, status_code=201)
async def create_retention_policy(
    request: Request,
    payload: DataRetentionPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DataRetentionPolicyRead:
    policy = data_lifecycle_service.create_retention_policy(db, payload, current_user)
    mark_request_target(request, policy.id, policy_version=policy.version)
    return policy


@router.get("/legal-holds", response_model=list[LegalHoldRead])
async def list_legal_holds(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[LegalHoldRead]:
    return data_lifecycle_service.list_legal_holds(db, current_user)


@router.post("/legal-holds", response_model=LegalHoldRead, status_code=201)
async def create_legal_hold(
    request: Request,
    payload: LegalHoldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> LegalHoldRead:
    hold = data_lifecycle_service.create_legal_hold(db, payload, current_user)
    mark_request_target(request, hold["id"], scope_type=hold["scope_type"], reason_code=hold["reason_code"])
    return hold


@router.post("/legal-holds/{hold_id}/release", response_model=LegalHoldRead)
async def release_legal_hold(
    request: Request,
    hold_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> LegalHoldRead:
    hold = data_lifecycle_service.release_legal_hold(db, hold_id, current_user)
    mark_request_target(request, hold["id"], scope_type=hold["scope_type"])
    return hold


@router.get("/deletion-requests", response_model=list[DataDeletionRequestRead])
async def list_deletion_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[DataDeletionRequestRead]:
    return data_lifecycle_service.list_deletion_requests(db, current_user)


@router.post("/deletion-requests", response_model=DataDeletionRequestRead, status_code=201)
async def create_deletion_request(
    request: Request,
    payload: DataDeletionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DataDeletionRequestRead:
    deletion = data_lifecycle_service.create_deletion_request(db, payload, current_user)
    mark_request_target(
        request,
        deletion["id"],
        scope_type=deletion["scope_type"],
        reason_code=deletion["reason_code"],
        policy_version=deletion["retention_policy_version"],
    )
    return deletion


@router.get("/deletion-requests/{request_id}", response_model=DataDeletionRequestRead)
async def get_deletion_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DataDeletionRequestRead:
    return data_lifecycle_service.get_deletion_request(db, request_id, current_user)


@router.post("/deletion-requests/{request_id}/approve", response_model=DataDeletionRequestRead)
async def approve_deletion_request(
    request: Request,
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DataDeletionRequestRead:
    deletion = data_lifecycle_service.approve_deletion_request(db, request_id, current_user)
    mark_request_target(request, deletion["id"], scope_type=deletion["scope_type"])
    return deletion


@router.post("/deletion-requests/{request_id}/cancel", response_model=DataDeletionRequestRead)
async def cancel_deletion_request(
    request: Request,
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DataDeletionRequestRead:
    deletion = data_lifecycle_service.cancel_deletion_request(db, request_id, current_user)
    mark_request_target(request, deletion["id"], scope_type=deletion["scope_type"])
    return deletion
