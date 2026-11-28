"""
FastAPI router for Member 3 (Sewer & Sanitation) ready for integration into
Member 4's BluePulse FastAPI backend.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from sewer_module.config import (
    ANOMALIES_OUTPUT_DIR,
    API_EXPORTS_DIR,
    RISK_OUTPUT_DIR,
    SCENARIO_DATA_DIR,
    get_scenario_specs,
)
from sewer_module.cross_contamination import assess_potential_cross_contamination
from sewer_module.schemas import (
    CrossContaminationRequest,
    ScenarioInfo,
    SpatialProximityRequest,
)
from sewer_module.spatial_analysis import analyze_water_sewer_proximity

router = APIRouter(prefix="/api/v1/sewer", tags=["Member 3 - Sewer & Sanitation"])


def _validate_scenario_name(scenario: str) -> str:
    specs = get_scenario_specs()
    if scenario not in specs:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. Available: {sorted(specs.keys())}",
        )
    return scenario


@router.get("/health")
def sewer_health() -> Dict[str, Any]:
    """Health check reporting available scenarios and precomputed outputs."""
    specs = get_scenario_specs()
    ready = [
        name for name in specs if (SCENARIO_DATA_DIR / f"{name}_step_readings.csv").exists()
    ]
    return {
        "module": "BluePulse Member 3 - Sewer & Sanitation",
        "status": "healthy",
        "configured_scenarios": list(specs.keys()),
        "simulated_scenarios_ready": ready,
    }


@router.get("/scenarios", response_model=List[ScenarioInfo])
def list_scenarios() -> List[ScenarioInfo]:
    """List all configured normal and fault hydraulic scenarios with assumptions."""
    specs = get_scenario_specs()
    return [
        ScenarioInfo(
            name=s.name,
            title=s.title,
            description=s.description,
            is_baseline=s.is_baseline,
            modifications=s.modifications,
            assumptions=s.assumptions,
            conduit_diameters_m=s.conduit_diameters_m,
        )
        for s in specs.values()
    ]


@router.get("/readings/{scenario}")
def get_scenario_readings(
    scenario: str,
    limit: int = Query(default=100, ge=1, le=2500),
    offset: int = Query(default=0, ge=0),
    resolution: str = Query(default="step", pattern="^(step|report)$"),
) -> Dict[str, Any]:
    """Return simulated sewer telemetry readings for a scenario."""
    _validate_scenario_name(scenario)
    suffix = "step_readings.csv" if resolution == "step" else "report_series.csv"
    csv_path = SCENARIO_DATA_DIR / f"{scenario}_{suffix}"
    if not csv_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Readings file not generated yet for '{scenario}'. Run pipeline first.",
        )

    df = pd.read_csv(csv_path)
    total = len(df)
    sliced = df.iloc[offset : offset + limit].copy()
    return {
        "scenario": scenario,
        "resolution": resolution,
        "total_records": total,
        "offset": offset,
        "returned_records": len(sliced),
        "records": sliced.to_dict(orient="records"),
    }


@router.get("/anomalies/{scenario}")
def get_scenario_anomalies(
    scenario: str,
    asset_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
) -> Dict[str, Any]:
    """Return interpretable anomaly alerts for a scenario."""
    _validate_scenario_name(scenario)
    alerts_path = ANOMALIES_OUTPUT_DIR / f"{scenario}_alerts.csv"
    if not alerts_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Anomaly alerts not generated yet for '{scenario}'.",
        )

    df = pd.read_csv(alerts_path) if alerts_path.stat().st_size > 2 else pd.DataFrame()
    if not df.empty:
        if asset_id:
            df = df[df["asset_id"] == asset_id]
        if severity:
            df = df[df["severity"].str.upper() == severity.upper()]
    total = len(df)
    sliced = df.head(limit)
    return {
        "scenario": scenario,
        "total_matching_alerts": total,
        "returned_alerts": len(sliced),
        "alerts": sliced.to_dict(orient="records"),
    }


@router.get("/risk/{scenario}")
def get_scenario_risk(scenario: str) -> Dict[str, Any]:
    """Return overflow risk summary and asset classification for a scenario."""
    _validate_scenario_name(scenario)
    summary_path = API_EXPORTS_DIR / "master_integration_summary.json"
    if summary_path.exists():
        master = json.loads(summary_path.read_text(encoding="utf-8"))
        if scenario in master.get("scenarios", {}):
            return master["scenarios"][scenario]["risk_summary"]

    risk_csv = RISK_OUTPUT_DIR / f"{scenario}_overflow_risk.csv"
    if not risk_csv.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Risk output not generated yet for '{scenario}'.",
        )
    df = pd.read_csv(risk_csv)
    return {
        "scenario": scenario,
        "records": len(df),
        "max_risk_score": float(df["risk_score"].max()) if not df.empty else 0.0,
    }


@router.post("/spatial/proximity")
def compute_spatial_proximity(payload: SpatialProximityRequest) -> Dict[str, Any]:
    """
    Compute projected metric distances between sewer assets and Member 1's
    drinking-water pipelines. Returns required schema if Member 1 data is absent.
    """
    try:
        return analyze_water_sewer_proximity(
            water_network_geojson=payload.water_network_geojson,
            water_crs=payload.water_crs,
            sewer_geojson=payload.sewer_geojson,
            sewer_crs=payload.sewer_crs,
            target_metric_crs=payload.target_metric_crs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/cross-contamination/assess")
def assess_cross_contamination(payload: CrossContaminationRequest) -> Dict[str, Any]:
    """
    Compute potential cross-contamination investigation priority combining
    Member 3 sewer state with Member 1 and Member 2 inputs (explicitly tracking missing fields).
    """
    return assess_potential_cross_contamination(
        sewer_asset_id=payload.sewer_asset_id,
        timestamp=payload.timestamp,
        sewer_hydraulic_state=payload.sewer_hydraulic_state,
        sewer_risk_score=payload.sewer_risk_score,
        distance_to_water_pipe_m=payload.distance_to_water_pipe_m,
        nearest_water_pipe_id=payload.nearest_water_pipe_id,
        water_pressure_bar=payload.water_pressure_bar,
        chlorine_residual_mg_l=payload.chlorine_residual_mg_l,
        turbidity_ntu=payload.turbidity_ntu,
    )


@router.get("/schemas/integration")
def get_integration_contracts() -> Dict[str, Any]:
    """Document exact JSON schemas required from Members 1, 2, and provided to Member 4."""
    contracts_path = API_EXPORTS_DIR / "integration_contracts.json"
    if contracts_path.exists():
        return json.loads(contracts_path.read_text(encoding="utf-8"))
    return {
        "member_3_outputs": [
            "simulation_readings",
            "fault_events",
            "anomaly_alerts",
            "overflow_risk_assessments",
            "spatial_proximity_results",
            "potential_cross_contamination_indicators",
        ],
        "awaiting_from_member_1": ["water_network_geojson", "crs", "water_pressure_bar"],
        "awaiting_from_member_2": ["chlorine_residual_mg_l", "turbidity_ntu"],
    }
