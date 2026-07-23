"""Authentication business logic."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Organization, User, UserSession
from ..security import create_access_token, verify_password
from ..settings import get_settings


def authenticate_user(db: Session, email: str, password: str) -> tuple[str, User, datetime]:
    """Validate credentials and return a raw session for cookie issuance."""

    user = db.scalar(
        select(User)
        .join(Organization, Organization.id == User.organization_id)
        .where(
            User.email == email.lower(),
            User.is_active.is_(True),
            Organization.lifecycle_status == "active",
        )
    )
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token, expires_at = create_access_token(db, user.id)
    return token, user, expires_at


def list_organization_users(db: Session, current_user: User) -> list[User]:
    """Return active users in the signed-in user's organization."""

    statement = select(User).where(User.organization_id == current_user.organization_id, User.is_active.is_(True)).order_by(User.full_name)
    return list(db.scalars(statement))


def list_active_sessions(db: Session, current_user: User) -> list[UserSession]:
    """Return active sessions in one organization without credential material."""

    now = datetime.now(timezone.utc)
    idle_cutoff = now - timedelta(minutes=get_settings().session_idle_timeout_minutes)
    statement = (
        select(UserSession)
        .options(selectinload(UserSession.user))
        .join(User, User.id == UserSession.user_id)
        .where(
            User.organization_id == current_user.organization_id,
            User.is_active.is_(True),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            UserSession.last_seen_at > idle_cutoff,
        )
        .order_by(UserSession.last_seen_at.desc(), UserSession.id)
    )
    return list(db.scalars(statement))


def revoke_organization_session(
    db: Session,
    current_user: User,
    session_id: UUID,
    current_session_id: UUID | None,
) -> UserSession:
    """Revoke one same-organization session while preserving the current login."""

    user_session = db.scalar(
        select(UserSession)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.id == session_id,
            User.organization_id == current_user.organization_id,
            UserSession.revoked_at.is_(None),
        )
    )
    if user_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active session not found")
    if user_session.id == current_session_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Use logout to revoke the current session")
    user_session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return user_session
