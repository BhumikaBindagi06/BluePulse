"""Core Pydantic models shared across BluePulse integration boundaries."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response payload for the API health check endpoint."""

    status: Literal["ok", "degraded"]
    environment: str
    database: Literal["ok", "error"]


class EvidenceItem(BaseModel):
    """Normalized piece of evidence collected from an upstream module or source."""

    id: str
    source: str
    summary: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiagnosisResult(BaseModel):
    """Structured diagnosis produced from collected evidence."""

    diagnosis_id: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class ImpactAssessment(BaseModel):
    """Assessment of operational or environmental impact for a diagnosis."""

    impact_id: str
    severity: Literal["low", "medium", "high", "critical"]
    affected_components: list[str] = Field(default_factory=list)
    summary: str

