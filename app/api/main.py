from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import get_settings
from app.api.routes import api_router
from app.database import get_async_engine
from app.metrics import metrics_app


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI lifespan handler to manage shared resources."""
    engine = get_async_engine()
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    fastapi_app = FastAPI(
        title="Poly Maker Control Plane",
        version="0.1.0",
        debug=settings.environment == "development",
        lifespan=lifespan,
    )
    
    # Configure CORS for local development and VPS deployment
    # Can be overridden via CORS_ORIGINS environment variable
    import os
    default_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    
    # Add VPS origins if VPS_IP is set
    vps_ip = os.getenv("VPS_IP", "")
    if vps_ip:
        vps_origins = [
            f"http://{vps_ip}:3000",
            f"http://{vps_ip}:3001",
            f"http://{vps_ip}:8000",
        ]
        default_origins.extend(vps_origins)
    
    # Add environment-specific origins (comma-separated)
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    if cors_origins_env:
        custom_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
        default_origins.extend(custom_origins)
    
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=default_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    
    fastapi_app.include_router(api_router)
    fastapi_app.mount("/metrics", metrics_app())
    return fastapi_app


app = create_app()


__all__ = ["app", "create_app"]

