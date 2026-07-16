"""Unauthenticated liveness and readiness probes for deployment platforms."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db


router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Confirm that the API process can accept requests."""

    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    """Confirm that the API process can reach its required database."""

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable") from error
    return {"status": "ok", "database": "reachable"}


@router.get("/health")
async def health(db: Session = Depends(get_db)) -> dict[str, str]:
    """Keep a concise readiness alias for operators and local smoke tests."""

    return await readiness(db)
