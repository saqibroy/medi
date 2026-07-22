"""Small Phase 1 auth helpers using only the Python standard library."""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserSession
from .settings import get_settings
from .csrf import session_cookie_name


bearer_scheme = HTTPBearer(auto_error=False)
SESSION_ACTIVITY_TOUCH_INTERVAL = timedelta(seconds=60)


def hash_password(password: str, salt: str | None = None) -> str:
    """Return a salted PBKDF2 password hash suitable for seeded demo users."""

    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), password_salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${password_salt}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    """Compare a submitted password with a stored hash."""

    try:
        algorithm, salt, expected = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    return hmac.compare_digest(hash_password(password, salt), f"{algorithm}${salt}${expected}")


def create_access_token(db: Session, user_id: UUID) -> tuple[str, datetime]:
    """Create a random, expiring session and store only its digest."""

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=get_settings().session_ttl_minutes)
    user_session = UserSession(user_id=user_id, token_digest=_token_digest(token), expires_at=expires_at, last_seen_at=now)
    db.add(user_session)
    db.commit()
    db.info["authenticated_session_id"] = user_session.id
    return token, expires_at


def _token_digest(token: str) -> str:
    return hmac.new(get_settings().token_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def resolve_access_session(db: Session, token: str) -> UserSession | None:
    """Resolve a raw bearer token to its active session without exposing it."""

    now = datetime.now(timezone.utc)
    idle_cutoff = now - timedelta(minutes=get_settings().session_idle_timeout_minutes)
    user_session = db.scalar(
        select(UserSession).where(
            UserSession.token_digest == _token_digest(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            UserSession.last_seen_at > idle_cutoff,
        )
    )
    if user_session is None or not user_session.user.is_active:
        return None
    last_seen_at = user_session.last_seen_at
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    if now - last_seen_at >= SESSION_ACTIVITY_TOUCH_INTERVAL:
        user_session.last_seen_at = now
        db.commit()
    return user_session


def resolve_access_token(db: Session, token: str) -> User | None:
    """Resolve one non-expired, non-revoked session into an active user."""

    user_session = resolve_access_session(db, token)
    return user_session.user if user_session is not None else None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve an explicit API bearer or the browser's HttpOnly session cookie."""

    raw_token = credentials.credentials if credentials is not None else request.cookies.get(session_cookie_name())
    if raw_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session")
    user_session = resolve_access_session(db, raw_token)
    if user_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    from .services.audit_service import mark_request_actor

    mark_request_actor(request, user_session.user, user_session.id)
    return user_session.user


def revoke_access_token(db: Session, token: str) -> UserSession | None:
    session = db.scalar(select(UserSession).where(UserSession.token_digest == _token_digest(token), UserSession.revoked_at.is_(None)))
    if session is not None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return session


def require_role(current_user: User, allowed_roles: set[str]) -> User:
    """Raise 403 unless the current user has one of the allowed roles."""

    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require an admin user for workspace setup actions."""

    return require_role(current_user, {"admin"})


async def require_annotator(current_user: User = Depends(get_current_user)) -> User:
    """Require a user who can create or edit annotations."""

    return require_role(current_user, {"admin", "annotator"})


async def require_reviewer(current_user: User = Depends(get_current_user)) -> User:
    """Require a user who can approve or reject annotations."""

    return require_role(current_user, {"admin", "reviewer"})
