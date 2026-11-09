"""Public liveness/readiness endpoint used by Docker healthchecks and deploy smoke tests."""

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_health_service
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health",
    description="Returns 200 when PostgreSQL and Redis are reachable, otherwise 503.",
    responses={503: {"model": HealthResponse, "description": "A dependency is unavailable"}},
)
async def health(
    response: Response, service: HealthService = Depends(get_health_service)
) -> HealthResponse:
    result = await service.check()
    if result.status != "ok":
        response.status_code = 503
    return result
