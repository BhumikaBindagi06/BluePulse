"""Tests for health endpoint, settings, and database session."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_health_endpoint() -> None:
    """GET /api/v1/health returns ok status and database connectivity."""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["environment"] == "development"


def test_settings_reads_env_file(tmp_path) -> None:
    """Settings loads overrides from an .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ENVIRONMENT=staging\nDATABASE_URL=sqlite:///./custom.db\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert settings.environment == "staging"
    assert settings.database_url == "sqlite:///./custom.db"

