"""Authentication business logic."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User
from ..security import create_access_token, verify_password


def authenticate_user(db: Session, email: str, password: str) -> tuple[str, User]:
    """Validate credentials and return a bearer token plus user."""

    user = db.scalar(select(User).where(User.email == email.lower(), User.is_active.is_(True)))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return create_access_token(user.id), user
