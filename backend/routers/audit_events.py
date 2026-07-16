"""Read-only, administrator-scoped security audit API."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import SecurityAuditEventRead
from ..security import require_admin
from ..services import audit_service


router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=list[SecurityAuditEventRead])
async def list_security_audit_events(
    action: str | None = Query(None, min_length=1, max_length=100),
    result: Literal["succeeded", "failed", "denied", "error"] | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[SecurityAuditEventRead]:
    """List only the signed-in administrator's organization events."""

    return audit_service.list_events(db, current_user, action=action, result=result, limit=limit, offset=offset)
