"""Authentication endpoints for the Medi product workspace."""

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AuthTokenRead, LoginRequest, UserRead
from ..security import bearer_scheme, get_current_user, revoke_access_token
from ..services import auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthTokenRead)
async def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthTokenRead:
    """Exchange demo user credentials for a bearer token."""

    token, user, expires_at = auth_service.authenticate_user(db, payload.email, payload.password)
    return AuthTokenRead(access_token=token, expires_at=expires_at, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    """Return the active user for the current bearer token."""

    return UserRead.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), db: Session = Depends(get_db)) -> None:
    """Revoke the current bearer session without exposing its value."""

    if credentials is not None:
        revoke_access_token(db, credentials.credentials)
