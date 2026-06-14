"""Authentication endpoints for the Medi product workspace."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AuthTokenRead, LoginRequest, UserRead
from ..security import get_current_user
from ..services import auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthTokenRead)
async def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthTokenRead:
    """Exchange demo user credentials for a bearer token."""

    token, user = auth_service.authenticate_user(db, payload.email, payload.password)
    return AuthTokenRead(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    """Return the active user for the current bearer token."""

    return UserRead.model_validate(current_user)
