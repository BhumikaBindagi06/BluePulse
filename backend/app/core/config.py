"""Application settings loaded from environment variables and .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the BluePulse backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BluePulse API"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./bluepulse.db"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

