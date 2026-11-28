"""
Automated test suite for BluePulse Sewer & Sanitation Module (Member 3).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from sewer_module.anomaly_detection import run_anomaly_detection
from sewer_module.config import (
    BLOCKAGE_INP_PATH,
    CORRECTED_HEAVY_RAINFALL_INP_PATH,
    LEGACY_BLOCKAGE_CSV,
    LEGACY_NORMAL_CSV,
    NORMAL_INP_PATH,
    SCENARIO_DATA_DIR,
    SCENARIO_MODELS_DIR,
    get_scenario_specs,
)
from sewer_module.cross_contamination import assess_potential_cross_contamination
from sewer_module.inp_builder import (
    generate_all_scenario_models,
    generate_corrected_heavy_rainfall_model,
)
from sewer_module.pipeline import verify_legacy_experimental_evidence
from sewer_module.risk_assessment import assess_overflow_risk, classify_hydraulic_state
from sewer_module.simulation import (
    manning_full_flow_cms,
    parse_rpt_summary,
    run_corrected_heavy_rainfall,
    run_scenario,
)
from sewer_module.spatial_analysis import analyze_water_sewer_proximity


def test_legacy_experimental_evidence_preserved() -> None:
    """Ensure existing 2,160-row CSV datasets and blockage findings remain intact."""
    assert LEGACY_NORMAL_CSV.exists()
    assert LEGACY_BLOCKAGE_CSV.exists()
    ev = verify_legacy_experimental_evidence()
    assert ev["available"] is True
    assert ev["normal_rows"] == 2160
    assert len(ev["normal_columns"]) == 11
    assert math.isclose(ev["normal_j2_mean_m"], 0.046065, abs_tol=1e-5)
    assert math.isclose(ev["j2_threshold_120pct_m"], 0.055278, abs_tol=1e-5)
    assert ev["blockage_j2_exceeded_count"] == 2131
    assert ev["blockage_j1_exceeded_count"] == 0
    assert ev["blockage_j3_exceeded_count"] == 0


def test_manning_capacity_matches_swmm_physics() -> None:
    """Check Manning full-pipe flow for 0.30 m conduit at S=0.01, n=0.013."""
    q_full = manning_full_flow_cms(diameter_m=0.30, slope=0.01, n=0.013)
    assert math.isclose(q_full, 0.09668, rel_tol=1e-3)


def test_scenario_models_generated_without_altering_originals() -> None:
    """Verify original .inp files exist and scenario models are created separately."""
    original_normal = NORMAL_INP_PATH.read_text(encoding="utf-8")
    original_blockage = BLOCKAGE_INP_PATH.read_text(encoding="utf-8")
    paths = generate_all_scenario_models(force=False)
    assert len(paths) == 6
    for name, p in paths.items():
        assert p.exists(), f"Missing model for {name}: {p}"
    assert NORMAL_INP_PATH.read_text(encoding="utf-8") == original_normal
    assert BLOCKAGE_INP_PATH.read_text(encoding="utf-8") == original_blockage


def test_simulation_and_rpt_parsing_heavy_rainfall() -> None:
    """Run heavy_rainfall SWMM scenario and verify surcharge, flooding, and velocities."""
    res = run_scenario("heavy_rainfall", save_outputs=False)
    assert len(res.step_df) >= 2160
    assert len(res.report_df) == 72
    assert res.step_df["J2_flooding_cms"].max() > 0.0
    assert res.report_df["C2_velocity_mps"].max() > 1.5
    assert abs(res.rpt_summary["continuity_error_pct"]) < 5.0
    assert len(res.rpt_summary["surcharged_nodes"]) == 3
    assert len(res.rpt_summary["flooded_nodes"]) >= 2


def test_anomaly_detection_baseline_vs_partial_blockage() -> None:
    """Verify normal baseline has low false positives while partial_blockage flags J2."""
    normal_df = pd.read_csv(SCENARIO_DATA_DIR / "normal_step_readings.csv")
    blockage_df = pd.read_csv(SCENARIO_DATA_DIR / "partial_blockage_step_readings.csv")

    norm_det = run_anomaly_detection(normal_df, normal_df, "normal_check", save_outputs=False)
    assert norm_det.node_stats["J2"]["threshold_exceeded_count"] == 0
    assert norm_det.isolation_forest_validation["validated"] is True
    assert norm_det.isolation_forest_validation["normal_false_positive_rate_pct"] <= 5.0

    blk_det = run_anomaly_detection(normal_df, blockage_df, "partial_blockage_check", save_outputs=False)
    assert blk_det.node_stats["J2"]["threshold_exceeded_count"] >= 2100
    assert blk_det.node_stats["J1"]["threshold_exceeded_count"] == 0
    assert blk_det.node_stats["J3"]["threshold_exceeded_count"] == 0
    assert not blk_det.alerts_df.empty
    assert "disclaimer" in blk_det.alerts_df.columns


def test_overflow_risk_state_distinction() -> None:
    """Ensure anomaly, surcharge, simulated flooding, and confirmed overflow are distinct."""
    assert classify_hydraulic_state(0.046, 2.0, 0.30, 0.046, 0.0) == "NORMAL"
    assert classify_hydraulic_state(0.062, 2.0, 0.30, 0.046, 0.0) == "ANOMALY_ONLY"
    assert classify_hydraulic_state(0.850, 2.0, 0.30, 0.046, 0.0) == "SURCHARGED"
    assert classify_hydraulic_state(2.000, 2.0, 0.30, 0.046, 0.05) == "FLOODING_SIMULATED"
    assert classify_hydraulic_state(2.000, 2.0, 0.30, 0.046, 0.05, field_overflow_confirmed=True) == "CONFIRMED_OVERFLOW"

    normal_df = pd.read_csv(SCENARIO_DATA_DIR / "normal_step_readings.csv")
    rain_df = pd.read_csv(SCENARIO_DATA_DIR / "heavy_rainfall_step_readings.csv")
    rain_risk = assess_overflow_risk(rain_df, normal_df, "heavy_rainfall_test", save_outputs=False)
    assert rain_risk.network_highest_status == "FLOODING_SIMULATED"
    assert rain_risk.network_max_risk_score >= 75.0


def test_spatial_analysis_requires_crs_and_reprojects_to_meters() -> None:
    """Verify missing Member 1 data is not fabricated, missing CRS fails, and WGS84 reprojects to UTM."""
    awaiting = analyze_water_sewer_proximity(water_network_geojson=None)
    assert awaiting["status"] == "awaiting_member1_water_network_data"
    assert awaiting["proximity_pairs"] == []

    # Synthetic test fixture ONLY for validating projected-CRS meter math
    water_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"pipe_id": "W_TEST_1", "diameter_m": 0.25, "material": "DI"},
                "geometry": {"type": "LineString", "coordinates": [[77.59460, 12.97160], [77.59560, 12.97160]]},
            }
        ],
    }
    sewer_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"asset_id": "C2", "asset_type": "sewer_conduit"},
                "geometry": {"type": "LineString", "coordinates": [[77.59460, 12.97169], [77.59560, 12.97169]]},
            }
        ],
    }

    with pytest.raises(ValueError, match="CRS is missing"):
        analyze_water_sewer_proximity(water_network_geojson=water_fc, sewer_geojson=sewer_fc)

    result = analyze_water_sewer_proximity(
        water_network_geojson=water_fc,
        water_crs="EPSG:4326",
        sewer_geojson=sewer_fc,
        sewer_crs="EPSG:4326",
    )
    assert result["status"] == "completed"
    assert result["distance_units"] == "meters"
    assert "32643" in result["projected_crs_used"]  # UTM Zone 43N
    # 0.00009 deg latitude ~ 10 meters
    dist = result["proximity_pairs"][0]["distance_m"]
    assert 8.0 < dist < 12.0


def test_cross_contamination_tracks_missing_inputs_and_never_claims_confirmed() -> None:
    """Ensure missing team inputs are explicit and status never claims confirmed contamination."""
    partial = assess_potential_cross_contamination(
        sewer_asset_id="J2",
        timestamp="2026-01-01T02:00:00",
        sewer_hydraulic_state="FLOODING_SIMULATED",
        sewer_risk_score=90.0,
    )
    assert partial["uncertainty_level"] == "HIGH"
    assert len(partial["missing_inputs"]) == 4
    assert "CONFIRMED" not in partial["status_label"]

    full = assess_potential_cross_contamination(
        sewer_asset_id="J2",
        timestamp="2026-01-01T02:00:00",
        sewer_hydraulic_state="FLOODING_SIMULATED",
        sewer_risk_score=90.0,
        nearest_water_pipe_id="W_1",
        distance_to_water_pipe_m=3.5,
        water_pressure_bar=0.1,
        chlorine_residual_mg_l=0.05,
        turbidity_ntu=7.2,
    )
    assert full["uncertainty_level"] == "LOW"
    assert full["missing_inputs"] == []
    assert full["potential_risk_score"] == 100.0
    assert full["status_label"] == "POTENTIAL_RISK_INVESTIGATION_ONLY"


def test_fastapi_integration_endpoints() -> None:
    """Verify Member 4 FastAPI router endpoints respond cleanly with standardized JSON."""
    client = TestClient(app)

    r_health = client.get("/api/v1/sewer/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "healthy"

    r_scen = client.get("/api/v1/sewer/scenarios")
    assert r_scen.status_code == 200
    assert len(r_scen.json()) == 6

    r_read = client.get("/api/v1/sewer/readings/normal?limit=5")
    assert r_read.status_code == 200
    assert r_read.json()["returned_records"] == 5

    r_anom = client.get("/api/v1/sewer/anomalies/partial_blockage?limit=5")
    assert r_anom.status_code == 200
    assert r_anom.json()["total_matching_alerts"] > 0

    r_risk = client.get("/api/v1/sewer/risk/heavy_rainfall")
    assert r_risk.status_code == 200
    assert r_risk.json()["network_highest_status"] == "FLOODING_SIMULATED"

    r_spat = client.post("/api/v1/sewer/spatial/proximity", json={})
    assert r_spat.status_code == 200
    assert r_spat.json()["status"] == "awaiting_member1_water_network_data"

    r_cc = client.post(
        "/api/v1/sewer/cross-contamination/assess",
        json={
            "sewer_asset_id": "J2",
            "timestamp": "2026-01-01T02:00:00",
            "sewer_hydraulic_state": "SURCHARGED",
            "sewer_risk_score": 65.0,
        },
    )
    assert r_cc.status_code == 200
    assert r_cc.json()["uncertainty_level"] == "HIGH"


def test_heavy_rainfall_corrected_eliminates_warning09() -> None:
    """
    Verify separate corrected heavy-rainfall model aligns RG1 interval (0:30) with STORM_TS,
    eliminating SWMM WARNING 09 while preserving the original heavy_rainfall .inp untouched.
    """
    orig_inp_path = SCENARIO_MODELS_DIR / "bluepulse_heavy_rainfall.inp"
    orig_inp_before = orig_inp_path.read_text(encoding="utf-8")

    corr_inp_path = generate_corrected_heavy_rainfall_model(force=False)
    assert corr_inp_path == CORRECTED_HEAVY_RAINFALL_INP_PATH
    assert corr_inp_path.exists()
    assert "RG1              INTENSITY 0:30" in corr_inp_path.read_text(encoding="utf-8")
    assert "RG1              INTENSITY 0:05" in orig_inp_before
    assert orig_inp_path.read_text(encoding="utf-8") == orig_inp_before

    corr_res = run_corrected_heavy_rainfall(save_outputs=False)
    assert corr_res.rpt_summary["warnings"] == []
    assert math.isclose(corr_res.rpt_summary["total_precipitation_mm"], 106.5, rel_tol=1e-3)
    assert abs(corr_res.rpt_summary["runoff_continuity_error_pct"]) < 1.0
    assert abs(corr_res.rpt_summary["continuity_error_pct"]) < 1.0
    total_flood_corr = sum(n["total_flood_volume_10e6_ltr"] for n in corr_res.rpt_summary["flooded_nodes"])
    assert total_flood_corr > 7.0


def test_overflow_risk_highest_connected_crown_and_manning_roughness() -> None:
    """
    Verify surcharge uses highest connected conduit crown (not only downstream diameter)
    and full-flow capacity uses scenario-specific Manning roughness.
    """
    normal_df = pd.read_csv(SCENARIO_DATA_DIR / "normal_step_readings.csv")
    specs = get_scenario_specs()

    # 1. severe_blockage: J2 connects C1 (0.30 m) and C2 (0.06 m, n=0.025)
    sev_spec = specs["severe_blockage"]
    sev_df = pd.read_csv(SCENARIO_DATA_DIR / "severe_blockage_step_readings.csv")
    sev_risk = assess_overflow_risk(
        step_df=sev_df,
        normal_df=normal_df,
        scenario_name="severe_blockage_check",
        conduit_diameters_m=sev_spec.conduit_diameters_m,
        save_outputs=False,
        conduit_roughness=sev_spec.conduit_roughness,
    )
    j2_sev = next(a for a in sev_risk.asset_summaries if a["asset_id"] == "J2")
    assert math.isclose(j2_sev["crown_height_m"], 0.30, abs_tol=1e-6)
    assert math.isclose(j2_sev["surcharged_minutes"] / 60.0, 5.71, abs_tol=0.02)
    j2_sev_ts = sev_risk.risk_timeseries_df[sev_risk.risk_timeseries_df["asset_id"] == "J2"]
    # Depths between 0.06 m and 0.30 m must be ANOMALY_ONLY (not SURCHARGED)
    between_crown = j2_sev_ts[(j2_sev_ts["depth_m"] > 0.06) & (j2_sev_ts["depth_m"] <= 0.30)]
    assert not between_crown.empty
    assert set(between_crown["hydraulic_state"].unique()) == {"ANOMALY_ONLY"}
    # C2 capacity ratio with n=0.025 matches SWMM Max/Full Flow (~1.45)
    assert math.isclose(float(j2_sev_ts["conduit_capacity_ratio"].max()), 1.45, rel_tol=0.02)

    # 2. downstream_siltation: J3 connects C2 (0.30 m) and C3 (0.08 m, n=0.030)
    silt_spec = specs["downstream_siltation"]
    silt_df = pd.read_csv(SCENARIO_DATA_DIR / "downstream_siltation_step_readings.csv")
    silt_risk = assess_overflow_risk(
        step_df=silt_df,
        normal_df=normal_df,
        scenario_name="downstream_siltation_check",
        conduit_diameters_m=silt_spec.conduit_diameters_m,
        save_outputs=False,
        conduit_roughness=silt_spec.conduit_roughness,
    )
    j3_silt = next(a for a in silt_risk.asset_summaries if a["asset_id"] == "J3")
    assert math.isclose(j3_silt["crown_height_m"], 0.30, abs_tol=1e-6)
    assert math.isclose(j3_silt["surcharged_minutes"] / 60.0, 5.62, abs_tol=0.02)
    j3_silt_ts = silt_risk.risk_timeseries_df[silt_risk.risk_timeseries_df["asset_id"] == "J3"]
    assert math.isclose(float(j3_silt_ts["conduit_capacity_ratio"].max()), 1.68, rel_tol=0.02)


def test_standalone_mode_explicitly_marks_missing_external_inputs() -> None:
    """
    Verify Member 3 operates independently when Member 1 and Member 2 data are unavailable,
    and explicitly represents missing external inputs as unavailable rather than 0.0.
    """
    client = TestClient(app)

    # Spatial proximity without Member 1 water network
    r_spat = client.post("/api/v1/sewer/spatial/proximity", json={})
    assert r_spat.status_code == 200
    assert r_spat.json()["status"] == "awaiting_member1_water_network_data"
    assert r_spat.json()["proximity_pairs"] == []

    # Malformed GeoJSON feature missing geometry returns 422 instead of 500
    r_bad_geom = client.post(
        "/api/v1/sewer/spatial/proximity",
        json={
            "water_network_geojson": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {"pipe_id": "W1"}}],
            },
            "water_crs": "EPSG:4326",
        },
    )
    assert r_bad_geom.status_code == 422

    # Missing Member 1 & 2 inputs must NOT be scored as 0.0 pressure/chlorine
    r_missing = client.post(
        "/api/v1/sewer/cross-contamination/assess",
        json={
            "sewer_asset_id": "J2",
            "timestamp": "2026-01-01T04:24:01",
            "sewer_hydraulic_state": "FLOODING_SIMULATED",
            "sewer_risk_score": 90.0,
        },
    )
    assert r_missing.status_code == 200
    body_missing = r_missing.json()
    assert body_missing["status_label"] == "INSUFFICIENT_DATA_AWAITING_TEAM_INPUTS"
    assert body_missing["investigation_priority"] == "INDETERMINATE_AWAITING_TEAM_INPUTS"
    assert body_missing["uncertainty_level"] == "HIGH"
    assert body_missing["input_completeness_pct"] == 20.0
    assert body_missing["score_breakdown"]["water_pressure_pts"] == 0.0
    assert body_missing["score_breakdown"]["water_quality_pts"] == 0.0
    assert len(body_missing["missing_inputs"]) == 4

    # Actual 0.0 bar / 0.0 mg/L measurements must be scored as real telemetry, not missing
    r_actual_zero = client.post(
        "/api/v1/sewer/cross-contamination/assess",
        json={
            "sewer_asset_id": "J2",
            "timestamp": "2026-01-01T04:24:01",
            "sewer_hydraulic_state": "FLOODING_SIMULATED",
            "sewer_risk_score": 90.0,
            "water_pressure_bar": 0.0,
            "chlorine_residual_mg_l": 0.0,
        },
    )
    assert r_actual_zero.status_code == 200
    body_zero = r_actual_zero.json()
    assert body_zero["score_breakdown"]["water_pressure_pts"] == 20.0
    assert body_zero["score_breakdown"]["water_quality_pts"] == 12.0
    assert len(body_zero["missing_inputs"]) == 2


def test_full_integration_workflow_with_synthetic_fixtures() -> None:
    """
    Exercise the full Member 3 -> Member 1 -> Member 2 -> Member 4 FastAPI workflow
    using clearly marked SYNTHETIC TEST FIXTURES ONLY.
    """
    fixtures_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_integration_fixtures.json"
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    assert fixtures["_synthetic_test_data"] is True

    client = TestClient(app)

    # 1. Member 3 risk output
    r_risk = client.get("/api/v1/sewer/risk/severe_blockage")
    assert r_risk.status_code == 200
    risk_data = r_risk.json()
    j2_summary = next(a for a in risk_data["asset_summaries"] if a["asset_id"] == "J2")

    # 2. Spatial proximity using synthetic Member 1 + synthetic georeferenced Member 3 GeoJSONs
    r_prox = client.post(
        "/api/v1/sewer/spatial/proximity",
        json={
            "water_network_geojson": fixtures["member1_water_network_geojson"],
            "water_crs": fixtures["water_crs"],
            "sewer_geojson": fixtures["member3_georeferenced_sewer_geojson"],
            "sewer_crs": fixtures["sewer_crs"],
        },
    )
    assert r_prox.status_code == 200
    prox_data = r_prox.json()
    assert prox_data["status"] == "completed"
    assert prox_data["distance_units"] == "meters"
    assert "32643" in prox_data["projected_crs_used"]
    j2_pair = next(p for p in prox_data["proximity_pairs"] if p["sewer_asset_id"] == "SYNTHETIC_TEST_J2")
    assert j2_pair["nearest_water_pipe_id"].startswith("SYNTHETIC_TEST_")
    assert j2_pair["proximity_tier"] == "CRITICAL_PROXIMITY"

    # 3. Cross-contamination assessment combining Member 3 state + synthetic Member 1 & Member 2
    p_case = fixtures["member1_pressure_cases"]["critical_low"]
    wq_case = fixtures["member2_water_quality_cases"]["contaminated_suspect"]
    r_cc = client.post(
        "/api/v1/sewer/cross-contamination/assess",
        json={
            "sewer_asset_id": "J2",
            "timestamp": "2026-01-01T04:24:01",
            "sewer_hydraulic_state": j2_summary["highest_hydraulic_state"],
            "sewer_risk_score": j2_summary["max_risk_score"],
            "nearest_water_pipe_id": j2_pair["nearest_water_pipe_id"],
            "distance_to_water_pipe_m": j2_pair["distance_m"],
            "water_pressure_bar": p_case["water_pressure_bar"],
            "chlorine_residual_mg_l": wq_case["chlorine_residual_mg_l"],
            "turbidity_ntu": wq_case["turbidity_ntu"],
        },
    )
    assert r_cc.status_code == 200
    cc_data = r_cc.json()
    assert cc_data["status_label"] == "POTENTIAL_RISK_INVESTIGATION_ONLY"
    assert cc_data["investigation_priority"] == "CRITICAL_INVESTIGATION_PRIORITY"
    assert cc_data["uncertainty_level"] == "LOW"
    assert cc_data["input_completeness_pct"] == 100.0
    assert cc_data["missing_inputs"] == []
    assert cc_data["potential_risk_score"] == 100.0
