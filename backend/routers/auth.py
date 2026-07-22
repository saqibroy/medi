"""Authentication endpoints for the Medi product workspace."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..csrf import create_csrf_token, csrf_cookie_name, session_cookie_name, set_csrf_cookie, set_session_cookie
from ..schemas import ActiveSessionRead, AuthSessionRead, CsrfTokenRead, LoginRequest, UserRead
from ..security import bearer_scheme, get_current_user, require_admin, revoke_access_token
from ..settings import get_settings
from ..services import auth_service
from ..services.audit_service import mark_request_actor


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/csrf", response_model=CsrfTokenRead)
async def csrf(request: Request, response: Response) -> CsrfTokenRead:
    """Issue a signed token bound to the current session, or to login intent."""

    settings = get_settings()
    binding = request.cookies.get(session_cookie_name(settings)) or "anonymous"
    token = create_csrf_token(binding, settings)
    set_csrf_cookie(response, token, settings)
    response.headers["Cache-Control"] = "no-store"
    return CsrfTokenRead(csrf_token=token)


@router.post("/login", response_model=AuthSessionRead)
async def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)) -> AuthSessionRead:
    """Authenticate and place the opaque session credential in an HttpOnly cookie."""

    token, user, expires_at = auth_service.authenticate_user(db, payload.email, payload.password)
    mark_request_actor(request, user, db.info.get("authenticated_session_id"))
    settings = get_settings()
    set_session_cookie(response, token, expires_at, settings)
    csrf_token = create_csrf_token(token, settings)
    set_csrf_cookie(response, csrf_token, settings)
    response.headers["Cache-Control"] = "no-store"
    return AuthSessionRead(expires_at=expires_at, csrf_token=csrf_token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    """Return the active user for the current browser or API session."""

    return UserRead.model_validate(current_user)


@router.get("/sessions", response_model=list[ActiveSessionRead])
async def list_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[ActiveSessionRead]:
    """Return credential-free active sessions for the current organization."""

    current_session_id = getattr(request.state, "audit_actor_session_id", None)
    idle_timeout = timedelta(minutes=get_settings().session_idle_timeout_minutes)
    return [
        ActiveSessionRead(
            id=user_session.id,
            user_id=user_session.user_id,
            user_email=user_session.user.email,
            created_at=user_session.created_at,
            last_seen_at=user_session.last_seen_at,
            idle_expires_at=user_session.last_seen_at + idle_timeout,
            absolute_expires_at=user_session.expires_at,
            current_session=user_session.id == current_session_id,
        )
        for user_session in auth_service.list_active_sessions(db, current_user)
    ]


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    """Revoke one active session belonging to the current organization."""

    auth_service.revoke_organization_session(
        db,
        current_user,
        session_id,
        getattr(request.state, "audit_actor_session_id", None),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: Session = Depends(get_db)) -> None:
    """Revoke the current session and clear both browser cookies."""

    settings = get_settings()
    raw_token = credentials.credentials if credentials is not None else request.cookies.get(session_cookie_name(settings))
    if raw_token is not None:
        user_session = revoke_access_token(db, raw_token)
        if user_session is not None:
            mark_request_actor(request, user_session.user, user_session.id)
    response.delete_cookie(session_cookie_name(settings), path="/", secure=settings.session_cookie_secure, httponly=True, samesite=settings.session_cookie_samesite)
    response.delete_cookie(csrf_cookie_name(settings), path="/", secure=settings.session_cookie_secure, httponly=False, samesite=settings.session_cookie_samesite)
