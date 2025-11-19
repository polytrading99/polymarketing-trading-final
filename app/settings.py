from typing import Optional

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized application configuration.

    Reads values from environment variables and optional .env files.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core service configuration
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # API service
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://poly:poly@localhost:5432/poly",
        alias="DATABASE_URL",
    )

    # Redis / cache
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")

    # External integrations
    polymarket_private_key: Optional[str] = Field(default=None, alias="PK")
    polymarket_browser_address: Optional[str] = Field(default=None, alias="BROWSER_ADDRESS")

    spreadsheet_url: Optional[AnyHttpUrl] = Field(default=None, alias="SPREADSHEET_URL")

    # Metrics & observability
    prometheus_multiprocess_dir: Optional[str] = Field(
        default=None, alias="PROMETHEUS_MULTIPROC_DIR"
    )


__all__ = ["Settings"]

