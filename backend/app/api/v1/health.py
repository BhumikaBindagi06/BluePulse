"""Health check endpoint."""

from bluepulse_contracts import HealthResponse
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import check_db_connection, get_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Verify API availability and database connectivity."""
    db_ok = check_db_connection(db)
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        environment=settings.environment,
        database="ok" if db_ok else "error",
    )

