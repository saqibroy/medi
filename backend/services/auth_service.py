"""Authentication business logic."""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User
from ..security import create_access_token, verify_password


def authenticate_user(db: Session, email: str, password: str) -> tuple[str, User, datetime]:
    """Validate credentials and return a raw session for cookie issuance."""

    user = db.scalar(select(User).where(User.email == email.lower(), User.is_active.is_(True)))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token, expires_at = create_access_token(db, user.id)
    return token, user, expires_at


def list_organization_users(db: Session, current_user: User) -> list[User]:
    """Return active users in the signed-in user's organization."""

    statement = select(User).where(User.organization_id == current_user.organization_id, User.is_active.is_(True)).order_by(User.full_name)
    return list(db.scalars(statement))
