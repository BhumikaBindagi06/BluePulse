"""
Transparent, explainable overflow risk assessment for BluePulse sewer junctions.

Explicitly distinguishes between:
- NORMAL: within baseline operating range
- ANOMALY_ONLY: statistically abnormal depth/flow, but water remains below pipe crown
- SURCHARGED: water rises above the pipe crown (pressurized flow), contained in manhole
- FLOODING_SIMULATED: SWMM reports active surface flooding / rim overflow (depth == max_depth)
- CONFIRMED_OVERFLOW: only assigned when field/physical sensor confirmation is supplied
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from sewer_module.config import (
    CONDUIT_ROUGHNESS,
    CONDUIT_SLOPE,
    DEFAULT_THRESHOLD_MULTIPLIER,
    JUNCTION_CONNECTED_CONDUITS,
    JUNCTION_IDS,
    JUNCTION_MAX_DEPTH_M,
    NORMAL_CONDUIT_DIAMETER_M,
    RISK_OUTPUT_DIR,
    ensure_output_directories,
)
from sewer_module.simulation import manning_full_flow_cms

# Downstream conduit connected to each junction (for crown-submergence surcharge check)
JUNCTION_DOWNSTREAM_CONDUIT: Dict[str, Tuple[str, str]] = {
    "J1": ("1", "C1"),
    "J2": ("2", "C2"),
    "J3": ("3", "C3"),
}


@dataclass
class RiskAssessmentResult:
    """Overflow risk time-series and per-asset summary for a simulation scenario."""

    scenario: str
    risk_timeseries_df: pd.DataFrame
    asset_summaries: List[Dict[str, Any]]
    network_max_risk_score: float
    network_highest_status: str
    risk_csv_path: Optional[Path] = None


def classify_hydraulic_state(
    depth_m: float,
    max_depth_m: float,
    crown_height_m: float,
    baseline_depth_m: float,
    flooding_cms: float,
    field_overflow_confirmed: bool = False,
) -> str:
    """
    Classify the hydraulic state of a manhole junction with strict separation
    between anomaly, surcharge, simulated flooding, and confirmed overflow.
    """
    if field_overflow_confirmed:
        return "CONFIRMED_OVERFLOW"
    if flooding_cms > 1e-6 or depth_m >= (max_depth_m - 1e-4):
        return "FLOODING_SIMULATED"
    if depth_m > crown_height_m:
        return "SURCHARGED"
    if baseline_depth_m > 0 and depth_m > baseline_depth_m * DEFAULT_THRESHOLD_MULTIPLIER:
        return "ANOMALY_ONLY"
    return "NORMAL"


def assess_overflow_risk(
    step_df: pd.DataFrame,
    normal_df: pd.DataFrame,
    scenario_name: str,
    conduit_diameters_m: Optional[Dict[str, float]] = None,
    report_df: Optional[pd.DataFrame] = None,
    field_confirmed_nodes: Optional[List[str]] = None,
    save_outputs: bool = True,
    conduit_roughness: Optional[Dict[str, float]] = None,
    conduit_slopes: Optional[Dict[str, float]] = None,
) -> RiskAssessmentResult:
    """
    Compute explainable 0-100 overflow risk scores at every step for J1, J2, and J3.

    Risk score formula (transparent, documented):
      1. Depth fill ratio (0-40 pts): 40 * min(1.0, depth / max_depth)
      2. Conduit capacity utilization (0-20 pts): 20 * min(1.0, flow / Q_full)
      3. Continuous abnormal duration (0-15 pts): 15 * min(1.0, abnormal_minutes / 60)
      4. Active rainfall contribution (0-10 pts): 10 * min(1.0, rainfall_mm_hr / 50)
      5. Surcharge / flooding severity (0-15 pts): +7.5 if surcharged (> crown), +15 if flooding (>0 CMS)
    """
    if step_df.empty or normal_df.empty:
        raise ValueError("step_df and normal_df must be non-empty.")

    ensure_output_directories()
    diameters = conduit_diameters_m or dict(NORMAL_CONDUIT_DIAMETER_M)
    roughness = conduit_roughness or dict(CONDUIT_ROUGHNESS)
    slopes = conduit_slopes or dict(CONDUIT_SLOPE)
    confirmed_set = set(field_confirmed_nodes or [])

    df = step_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Step duration in minutes (typically 10 s = 1/6 min)
    if len(df) >= 2:
        dt_minutes = max(
            0.01,
            float((df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds() / 60.0),
        )
    else:
        dt_minutes = 1.0 / 6.0

    # Align 5-min rainfall series onto 10-sec step_df if report_df is provided
    rainfall_series = pd.Series(0.0, index=df.index)
    if report_df is not None and not report_df.empty and "system_rainfall_mm_hr" in report_df.columns:
        rdf = report_df[["timestamp", "system_rainfall_mm_hr"]].copy()
        rdf["timestamp"] = pd.to_datetime(rdf["timestamp"])
        merged = pd.merge_asof(
            df[["timestamp"]].sort_values("timestamp"),
            rdf.sort_values("timestamp"),
            on="timestamp",
            direction="nearest",
        )
        rainfall_series = merged["system_rainfall_mm_hr"].fillna(0.0).reset_index(drop=True)

    baseline_depths = {
        nid: float(normal_df[f"{nid}_depth_m"].mean()) for nid in JUNCTION_IDS
    }

    risk_rows: List[Dict[str, Any]] = []
    asset_summaries: List[Dict[str, Any]] = []
    status_rank = {
        "NORMAL": 0,
        "ANOMALY_ONLY": 1,
        "SURCHARGED": 2,
        "FLOODING_SIMULATED": 3,
        "CONFIRMED_OVERFLOW": 4,
    }

    for nid in JUNCTION_IDS:
        swmm_cid, label_cid = JUNCTION_DOWNSTREAM_CONDUIT[nid]
        # SWMM defines node surcharge relative to the highest connected conduit crown (InOffset=OutOffset=0)
        connected_cids = JUNCTION_CONNECTED_CONDUITS.get(nid, [swmm_cid])
        crown_m = max(float(diameters.get(cid, 0.30)) for cid in connected_cids)
        max_depth_m = float(JUNCTION_MAX_DEPTH_M[nid])
        base_d = baseline_depths[nid]

        q_full = manning_full_flow_cms(
            diameter_m=float(diameters.get(swmm_cid, 0.30)),
            slope=float(slopes.get(swmm_cid, 0.01)),
            n=float(roughness.get(swmm_cid, 0.013)),
        )

        depth_col = f"{nid}_depth_m"
        flood_col = f"{nid}_flooding_cms"
        flow_col = f"{label_cid}_flow_cms"
        cap_col = f"{label_cid}_flow_capacity_ratio"
        use_flow_for_cap = flow_col in df.columns and q_full > 0

        continuous_abnormal_min = 0.0
        node_scores: List[float] = []
        node_states: List[str] = []
        surcharged_steps = 0
        flooded_steps = 0

        for idx, row in df.iterrows():
            depth = float(row[depth_col])
            flooding = float(row.get(flood_col, 0.0))
            if use_flow_for_cap:
                cap_ratio = abs(float(row[flow_col])) / q_full
            else:
                cap_ratio = float(row.get(cap_col, 0.0))
            rain = float(rainfall_series.iloc[idx]) if idx < len(rainfall_series) else 0.0

            state = classify_hydraulic_state(
                depth_m=depth,
                max_depth_m=max_depth_m,
                crown_height_m=crown_m,
                baseline_depth_m=base_d,
                flooding_cms=flooding,
                field_overflow_confirmed=(nid in confirmed_set and flooding > 0),
            )

            if state != "NORMAL":
                continuous_abnormal_min += dt_minutes
            else:
                continuous_abnormal_min = 0.0

            if state in ("SURCHARGED", "FLOODING_SIMULATED", "CONFIRMED_OVERFLOW"):
                surcharged_steps += 1
            if state in ("FLOODING_SIMULATED", "CONFIRMED_OVERFLOW"):
                flooded_steps += 1

            depth_ratio = min(1.0, max(0.0, depth / max_depth_m))
            depth_pts = 40.0 * depth_ratio
            cap_pts = 20.0 * min(1.0, max(0.0, cap_ratio))
            dur_pts = 15.0 * min(1.0, continuous_abnormal_min / 60.0)
            rain_pts = 10.0 * min(1.0, max(0.0, rain / 50.0))
            if state in ("FLOODING_SIMULATED", "CONFIRMED_OVERFLOW"):
                state_pts = 15.0
            elif state == "SURCHARGED":
                state_pts = 7.5
            else:
                state_pts = 0.0

            total_score = round(min(100.0, depth_pts + cap_pts + dur_pts + rain_pts + state_pts), 2)
            node_scores.append(total_score)
            node_states.append(state)

            risk_rows.append(
                {
                    "timestamp": row["timestamp"].isoformat(),
                    "scenario": scenario_name,
                    "asset_id": nid,
                    "depth_m": round(depth, 6),
                    "max_depth_m": max_depth_m,
                    "depth_ratio": round(depth_ratio, 4),
                    "crown_height_m": crown_m,
                    "flooding_cms": round(flooding, 6),
                    "conduit_capacity_ratio": round(cap_ratio, 4),
                    "rainfall_mm_hr": round(rain, 2),
                    "abnormal_duration_min": round(continuous_abnormal_min, 2),
                    "hydraulic_state": state,
                    "risk_score": total_score,
                    "risk_tier": (
                        "CRITICAL" if total_score >= 75 else
                        "HIGH" if total_score >= 50 else
                        "MODERATE" if total_score >= 25 else
                        "LOW"
                    ),
                }
            )

        highest_state = max(node_states, key=lambda s: status_rank[s])
        max_score = max(node_scores) if node_scores else 0.0
        mean_score = sum(node_scores) / len(node_scores) if node_scores else 0.0

        asset_summaries.append(
            {
                "asset_id": nid,
                "scenario": scenario_name,
                "baseline_depth_m": round(base_d, 6),
                "max_depth_m_observed": round(float(df[depth_col].max()), 6),
                "manhole_rim_depth_m": max_depth_m,
                "max_depth_fill_pct": round(float(df[depth_col].max()) / max_depth_m * 100.0, 2),
                "connected_downstream_conduit": label_cid,
                "crown_height_m": crown_m,
                "surcharged_minutes": round(surcharged_steps * dt_minutes, 2),
                "flooded_minutes": round(flooded_steps * dt_minutes, 2),
                "max_flooding_cms": round(float(df[flood_col].max()), 6) if flood_col in df.columns else 0.0,
                "max_risk_score": round(max_score, 2),
                "mean_risk_score": round(mean_score, 2),
                "highest_hydraulic_state": highest_state,
            }
        )

    risk_df = pd.DataFrame(risk_rows)
    risk_csv_path = RISK_OUTPUT_DIR / f"{scenario_name}_overflow_risk.csv"
    if save_outputs:
        risk_df.to_csv(risk_csv_path, index=False)

    network_max = max((a["max_risk_score"] for a in asset_summaries), default=0.0)
    network_state = max(
        (a["highest_hydraulic_state"] for a in asset_summaries),
        key=lambda s: status_rank[s],
        default="NORMAL",
    )

    return RiskAssessmentResult(
        scenario=scenario_name,
        risk_timeseries_df=risk_df,
        asset_summaries=asset_summaries,
        network_max_risk_score=round(network_max, 2),
        network_highest_status=network_state,
        risk_csv_path=risk_csv_path if save_outputs else None,
    )
