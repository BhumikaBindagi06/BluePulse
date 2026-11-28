"""
End-to-end orchestration pipeline for BluePulse Member 3 (Sewer & Sanitation).

Executes:
1. Generation of separate fault-scenario SWMM .inp models (preserving originals).
2. PySWMM hydraulic simulations + SWMM .out/.rpt extraction for all scenarios.
3. Multi-method anomaly detection (threshold, Z-score, validated Isolation Forest)
   plus reproduction check against preserved legacy CSVs.
4. Explainable overflow risk assessment distinguishing anomaly/surcharge/flooding/overflow.
5. Spatial proximity readiness check (awaiting Member 1 water-network GeoJSON).
6. Potential cross-contamination risk assessment (explicitly tracking missing Member 1/2 inputs).
7. Matplotlib visualizations and standardized JSON/CSV exports for Member 4.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import pandas as pd

from sewer_module.anomaly_detection import run_anomaly_detection
from sewer_module.config import (
    API_EXPORTS_DIR,
    LEGACY_BLOCKAGE_CSV,
    LEGACY_NORMAL_CSV,
    ensure_output_directories,
    get_scenario_specs,
)
from sewer_module.cross_contamination import assess_potential_cross_contamination
from sewer_module.inp_builder import generate_all_scenario_models
from sewer_module.risk_assessment import assess_overflow_risk
from sewer_module.simulation import run_scenario
from sewer_module.spatial_analysis import analyze_water_sewer_proximity
from sewer_module.visualization import (
    plot_multi_scenario_c2_velocity_and_flow,
    plot_multi_scenario_j2_depth,
    plot_overflow_risk_timeline,
    plot_scenario_junction_depths,
)

logger = logging.getLogger(__name__)


def verify_legacy_experimental_evidence() -> Dict[str, Any]:
    """
    Verify and report the preserved existing experimental results from
    data/normal_readings.csv and data/blockage_readings.csv without modifying them.
    """
    if not LEGACY_NORMAL_CSV.exists() or not LEGACY_BLOCKAGE_CSV.exists():
        return {"available": False}

    normal = pd.read_csv(LEGACY_NORMAL_CSV)
    blockage = pd.read_csv(LEGACY_BLOCKAGE_CSV)
    j2_mean = float(normal["J2_depth_m"].mean())
    j2_thresh = j2_mean * 1.20
    j1_thresh = float(normal["J1_depth_m"].mean()) * 1.20
    j3_thresh = float(normal["J3_depth_m"].mean()) * 1.20

    return {
        "available": True,
        "normal_rows": int(len(normal)),
        "normal_columns": list(normal.columns),
        "blockage_rows": int(len(blockage)),
        "normal_j2_mean_m": round(j2_mean, 6),
        "j2_threshold_120pct_m": round(j2_thresh, 6),
        "blockage_j2_exceeded_count": int((blockage["J2_depth_m"] > j2_thresh).sum()),
        "blockage_j1_exceeded_count": int((blockage["J1_depth_m"] > j1_thresh).sum()),
        "blockage_j3_exceeded_count": int((blockage["J3_depth_m"] > j3_thresh).sum()),
        "note": (
            "Preserved original datasets. Note: legacy extract_readings.py recorded link.depth "
            "into C*_velocity_mps; the new sewer_module/simulation.py extracts true SWMM hydraulic "
            "velocities into data/outputs/simulations/."
        ),
    }


def run_full_pipeline() -> Dict[str, Any]:
    """Execute the full Member 3 simulation, monitoring, risk, and export pipeline."""
    ensure_output_directories()
    generate_all_scenario_models(force=True)

    specs = get_scenario_specs()
    sim_results = {}
    for name in specs:
        sim_results[name] = run_scenario(name, save_outputs=True)

    normal_step_df = sim_results["normal"].step_df

    scenario_dfs: Dict[str, pd.DataFrame] = {}
    risk_dfs: Dict[str, pd.DataFrame] = {}
    master_scenarios: Dict[str, Any] = {}
    fault_events: List[Dict[str, Any]] = []
    cross_contam_indicators: List[Dict[str, Any]] = []

    for name, sim_res in sim_results.items():
        spec = specs[name]
        scenario_dfs[name] = sim_res.step_df

        det = run_anomaly_detection(
            normal_df=normal_step_df,
            target_df=sim_res.step_df,
            scenario_name=name,
            save_outputs=True,
        )

        risk = assess_overflow_risk(
            step_df=sim_res.step_df,
            normal_df=normal_step_df,
            scenario_name=name,
            conduit_diameters_m=spec.conduit_diameters_m,
            report_df=sim_res.report_df,
            save_outputs=True,
            conduit_roughness=spec.conduit_roughness,
        )
        risk_dfs[name] = risk.risk_timeseries_df

        plot_scenario_junction_depths(name, sim_res.step_df)

        # Pick peak risk junction event for cross-contamination readiness indicator
        peak_asset = max(risk.asset_summaries, key=lambda a: a["max_risk_score"])
        peak_row = (
            risk.risk_timeseries_df.sort_values("risk_score", ascending=False).iloc[0]
            if not risk.risk_timeseries_df.empty
            else None
        )
        if peak_row is not None and not spec.is_baseline:
            fault_events.append(
                {
                    "scenario": name,
                    "title": spec.title,
                    "peak_timestamp": str(peak_row["timestamp"]),
                    "primary_affected_asset": str(peak_row["asset_id"]),
                    "highest_hydraulic_state": risk.network_highest_status,
                    "max_risk_score": risk.network_max_risk_score,
                    "alert_count": int(len(det.alerts_df)),
                    "modifications": spec.modifications,
                }
            )
            cross_contam_indicators.append(
                assess_potential_cross_contamination(
                    sewer_asset_id=str(peak_row["asset_id"]),
                    timestamp=str(peak_row["timestamp"]),
                    sewer_hydraulic_state=str(peak_row["hydraulic_state"]),
                    sewer_risk_score=float(peak_row["risk_score"]),
                )
            )

        master_scenarios[name] = {
            "title": spec.title,
            "is_baseline": spec.is_baseline,
            "modifications": spec.modifications,
            "assumptions": spec.assumptions,
            "step_readings_csv": str(sim_res.step_csv_path),
            "report_series_csv": str(sim_res.report_csv_path),
            "rpt_summary": sim_res.rpt_summary,
            "anomaly_summary": {
                "total_alerts": int(len(det.alerts_df)),
                "node_stats": det.node_stats,
                "conduit_stats": det.conduit_stats,
                "isolation_forest_validation": det.isolation_forest_validation,
                "alerts_csv": str(det.alerts_csv_path),
            },
            "risk_summary": {
                "network_max_risk_score": risk.network_max_risk_score,
                "network_highest_status": risk.network_highest_status,
                "asset_summaries": risk.asset_summaries,
                "risk_csv": str(risk.risk_csv_path),
            },
        }

    # Multi-scenario comparison visualizations
    plot_j2 = plot_multi_scenario_j2_depth(scenario_dfs)
    plot_c2 = plot_multi_scenario_c2_velocity_and_flow(scenario_dfs)
    plot_risk = plot_overflow_risk_timeline(risk_dfs)

    # Spatial readiness (no fabricated water pipes!)
    spatial_status = analyze_water_sewer_proximity(water_network_geojson=None)

    # Legacy check
    legacy_evidence = verify_legacy_experimental_evidence()

    # Standardized Member 4 integration exports
    (API_EXPORTS_DIR / "fault_events.json").write_text(
        json.dumps(fault_events, indent=2), encoding="utf-8"
    )
    (API_EXPORTS_DIR / "spatial_proximity_status.json").write_text(
        json.dumps(spatial_status, indent=2), encoding="utf-8"
    )
    (API_EXPORTS_DIR / "cross_contamination_indicators.json").write_text(
        json.dumps(cross_contam_indicators, indent=2), encoding="utf-8"
    )

    integration_contracts = {
        "module": "BluePulse Member 3 - Sewer & Sanitation",
        "fastapi_router_import": "from sewer_module.api import router as sewer_router",
        "endpoints": [
            "GET /api/v1/sewer/health",
            "GET /api/v1/sewer/scenarios",
            "GET /api/v1/sewer/readings/{scenario}",
            "GET /api/v1/sewer/anomalies/{scenario}",
            "GET /api/v1/sewer/risk/{scenario}",
            "POST /api/v1/sewer/spatial/proximity",
            "POST /api/v1/sewer/cross-contamination/assess",
            "GET /api/v1/sewer/schemas/integration",
        ],
        "required_from_member_1": {
            "water_network_geojson": "GeoJSON FeatureCollection of drinking-water pipelines with CRS (e.g. EPSG:4326 or UTM)",
            "sewer_geojson": "GeoJSON FeatureCollection of georeferenced sewer pipes/nodes matching real-world CRS",
            "water_pressure_bar": "Per-pipe or per-zone drinking-water pressure telemetry (bar)",
        },
        "required_from_member_2": {
            "chlorine_residual_mg_l": "Free chlorine residual readings (mg/L)",
            "turbidity_ntu": "Water turbidity readings (NTU)",
        },
    }
    (API_EXPORTS_DIR / "integration_contracts.json").write_text(
        json.dumps(integration_contracts, indent=2), encoding="utf-8"
    )

    master_summary = {
        "legacy_experimental_evidence": legacy_evidence,
        "plots": {
            "j2_depth_comparison": str(plot_j2),
            "c2_flow_velocity_comparison": str(plot_c2),
            "overflow_risk_timeline": str(plot_risk),
        },
        "spatial_proximity_status": spatial_status,
        "cross_contamination_indicators": cross_contam_indicators,
        "scenarios": master_scenarios,
    }
    (API_EXPORTS_DIR / "master_integration_summary.json").write_text(
        json.dumps(master_summary, indent=2), encoding="utf-8"
    )

    return master_summary
