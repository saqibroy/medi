"""Small Phase 1 auth helpers using only the Python standard library."""

import base64
import hashlib
import hmac
import secrets
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .settings import get_settings


bearer_scheme = HTTPBearer(auto_error=False)


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


def create_access_token(user_id: UUID) -> str:
    """Create a signed bearer token containing only the user id."""

    payload = str(user_id)
    signature = hmac.new(get_settings().token_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token_bytes = f"{payload}.{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(token_bytes).decode("ascii")


def parse_access_token(token: str) -> UUID | None:
    """Validate a token signature and return its user id."""

    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        payload, signature = decoded.rsplit(".", 1)
        expected = hmac.new(get_settings().token_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        return UUID(payload)
    except (ValueError, UnicodeDecodeError):
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency that resolves the bearer token into an active user."""

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    user_id = parse_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


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
