"""Workspace user endpoints for assignment and collaboration UI."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import UserRead
from ..security import get_current_user
from ..services import auth_service


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[UserRead]:
    """Return active users in the current organization."""

    return [UserRead.model_validate(user) for user in auth_service.list_organization_users(db, current_user)]
