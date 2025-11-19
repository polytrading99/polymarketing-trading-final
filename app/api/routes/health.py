from fastapi import APIRouter

from app import get_settings

router = APIRouter(prefix="/health")


@router.get("/", summary="Service health check")
async def healthcheck() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
    }

