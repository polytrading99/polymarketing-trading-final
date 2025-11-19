"""Top-level package for the modernized Poly-Maker application."""

from functools import lru_cache

from .settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]

