"""Health and readiness check endpoints."""

from fastapi import APIRouter, status, Response
from api.db.session import check_db_health

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Lightweight Kubernetes/Docker liveness probe."""
    return {"status": "live"}


@router.get("/ready")
async def readiness_probe(response: Response):
    """Readiness probe checking database connectivity without exposing connection details."""
    is_ready = await check_db_health()
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unavailable"}

    return {"status": "ready", "database": "connected"}
