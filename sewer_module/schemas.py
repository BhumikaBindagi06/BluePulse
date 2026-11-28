"""
Standardized Pydantic schemas for BluePulse Member 4 (FastAPI backend) integration,
plus explicit input contracts for Member 1 (water network / pressure / spatial)
and Member 2 (water quality sensors).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScenarioInfo(BaseModel):
    name: str
    title: str
    description: str
    is_baseline: bool
    modifications: List[str]
    assumptions: List[str]
    conduit_diameters_m: Dict[str, float]


class SimulationReadingRecord(BaseModel):
    timestamp: str
    scenario: str
    J1_depth_m: float
    J2_depth_m: float
    J3_depth_m: float
    O1_depth_m: float
    C1_flow_cms: float
    C2_flow_cms: float
    C3_flow_cms: float
    C1_velocity_mps: float
    C2_velocity_mps: float
    C3_velocity_mps: float


class AnomalyAlertRecord(BaseModel):
    timestamp: str
    scenario: str
    asset_id: str
    asset_type: str
    metric: str
    observed_value: float
    baseline_value: float
    threshold: float
    z_score: float
    detection_method: str
    severity: str
    suspected_condition: str
    disclaimer: str


class AssetRiskSummary(BaseModel):
    asset_id: str
    scenario: str
    baseline_depth_m: float
    max_depth_m_observed: float
    manhole_rim_depth_m: float
    max_depth_fill_pct: float
    connected_downstream_conduit: str
    crown_height_m: float
    surcharged_minutes: float
    flooded_minutes: float
    max_flooding_cms: float
    max_risk_score: float
    mean_risk_score: float
    highest_hydraulic_state: str


class SpatialProximityRequest(BaseModel):
    """Input contract expected from Member 1 for real-world spatial proximity."""

    water_network_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="GeoJSON FeatureCollection of drinking-water pipes from Member 1.",
    )
    water_crs: Optional[str] = Field(
        default=None,
        description="CRS of water_network_geojson, e.g. 'EPSG:4326' or 'EPSG:32643'.",
    )
    sewer_geojson: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Georeferenced GeoJSON FeatureCollection of sewer assets (required when water_network_geojson is supplied).",
    )
    sewer_crs: Optional[str] = Field(
        default=None,
        description="CRS of sewer_geojson.",
    )
    target_metric_crs: Optional[str] = Field(
        default=None,
        description="Optional projected CRS in meters; if omitted, UTM is auto-estimated.",
    )


class CrossContaminationRequest(BaseModel):
    """Combined input contract across Member 3, Member 1, and Member 2."""

    sewer_asset_id: str = Field(..., examples=["J2"])
    timestamp: str = Field(..., examples=["2026-01-01T02:00:00"])
    sewer_hydraulic_state: str = Field(..., examples=["FLOODING_SIMULATED"])
    sewer_risk_score: float = Field(..., ge=0.0, le=100.0, examples=[85.0])
    # Member 1 inputs (optional until Member 1 provides live values)
    nearest_water_pipe_id: Optional[str] = Field(default=None, examples=["W_MAIN_12"])
    distance_to_water_pipe_m: Optional[float] = Field(default=None, ge=0.0, examples=[4.2])
    water_pressure_bar: Optional[float] = Field(default=None, examples=[0.4])
    # Member 2 inputs (optional until Member 2 provides live values)
    chlorine_residual_mg_l: Optional[float] = Field(default=None, ge=0.0, examples=[0.12])
    turbidity_ntu: Optional[float] = Field(default=None, ge=0.0, examples=[6.5])
