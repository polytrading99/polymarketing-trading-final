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
    
    # Configure CORS
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
        ],
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

