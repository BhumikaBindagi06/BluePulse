"""
Multi-method hydraulic anomaly detection for BluePulse sewer monitoring.

Implements:
1. Threshold-based detection (compatible with existing 120% baseline rule + low-flow drop checks).
2. Z-score statistical detection with noise-floor protection.
3. Optional Isolation Forest multivariate detection, validated against the normal baseline.
4. Interpretable alert generation with explicit hydraulic disclaimers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from sewer_module.config import (
    ANOMALIES_OUTPUT_DIR,
    DEFAULT_THRESHOLD_MULTIPLIER,
    DEFAULT_ZSCORE_THRESHOLD,
    JUNCTION_IDS,
    MIN_STD_FLOOR_FLOW_CMS,
    MIN_STD_FLOOR_M,
    MIN_STD_FLOOR_VEL_MPS,
    ensure_output_directories,
)

logger = logging.getLogger(__name__)

CONDUIT_LABELS = ["C1", "C2", "C3"]
DEFAULT_ML_FEATURES = [
    "J1_depth_m",
    "J2_depth_m",
    "J3_depth_m",
    "C1_flow_cms",
    "C2_flow_cms",
    "C3_flow_cms",
    "C1_velocity_mps",
    "C2_velocity_mps",
    "C3_velocity_mps",
]


@dataclass
class DetectionSummary:
    """Summary of anomaly detection outputs for a scenario."""

    scenario: str
    total_readings: int
    node_stats: Dict[str, Dict[str, Any]]
    conduit_stats: Dict[str, Dict[str, Any]]
    isolation_forest_validation: Dict[str, Any]
    alerts_df: pd.DataFrame
    annotated_df: pd.DataFrame
    alerts_csv_path: Optional[Path] = None


def _safe_std(series: pd.Series, floor: float) -> float:
    """Compute standard deviation with a physical noise floor to avoid zero-division."""
    raw = float(series.std(ddof=0)) if len(series) > 0 else 0.0
    if np.isnan(raw):
        return floor
    return max(raw, floor)


def _infer_suspected_condition(
    row: pd.Series,
    asset_id: str,
    metric: str,
    direction: str,
    baselines: Dict[str, float],
) -> str:
    """
    Provide a beginner-friendly suspected physical explanation based on spatial
    patterns across J1, J2, J3 and C1, C2, C3. Always framed as a hypothesis,
    never as confirmed fault proof.
    """
    j1 = float(row.get("J1_depth_m", 0.0))
    j2 = float(row.get("J2_depth_m", 0.0))
    j3 = float(row.get("J3_depth_m", 0.0))
    c1 = float(row.get("C1_flow_cms", 0.0))
    c2 = float(row.get("C2_flow_cms", 0.0))
    c3 = float(row.get("C3_flow_cms", 0.0))

    b_j1 = baselines.get("J1_depth_m", 0.05)
    b_j2 = baselines.get("J2_depth_m", 0.05)
    b_j3 = baselines.get("J3_depth_m", 0.05)
    b_c2 = baselines.get("C2_flow_cms", 0.005)
    b_c3 = baselines.get("C3_flow_cms", 0.005)

    # All nodes elevated + high flow -> storm runoff or network-wide surge
    if j1 > b_j1 * 2.0 and j2 > b_j2 * 2.0 and j3 > b_j3 * 2.0 and c2 > b_c2 * 2.0:
        return "Suspected wet-weather storm runoff or high network-wide inflow"

    # J2 elevated, C2 flow surging -> sudden inflow at J2
    if j2 > b_j2 * 2.0 and c2 > b_c2 * 2.0 and c1 < c2 * 0.5:
        return "Suspected sudden lateral inflow or abnormal discharge near J2"

    # J3 elevated, C3 flow suppressed -> downstream obstruction in C3
    if j3 > b_j3 * 1.2 and c3 <= b_c3 * 0.85:
        return "Suspected downstream obstruction or siltation in Conduit C3"

    # J2 elevated, J3 normal/low or C2 flow suppressed -> blockage in C2
    if asset_id in ("J2", "C2") and j2 > b_j2 * 1.2 and j3 <= b_j3 * 1.2:
        return "Suspected partial or severe blockage in Conduit C2 (J2->J3)"

    if direction == "low" and "flow" in metric:
        return f"Suspected upstream flow restriction or blockage affecting {asset_id}"

    if direction == "low" and "velocity" in metric:
        return f"Suspected backwater ponding or low-velocity sediment risk in {asset_id}"

    if direction == "high" and "velocity" in metric:
        return f"Suspected high-velocity surge or constricted cross-section in {asset_id}"

    return f"Unusual hydraulic behavior observed at {asset_id} ({metric}); inspect upstream/downstream assets"


def _compute_severity(ratio: float, z_score: float, is_flooding: bool = False) -> str:
    """Map deviation magnitude to a transparent severity tier."""
    if is_flooding or ratio >= 5.0 or abs(z_score) >= 20.0:
        return "CRITICAL"
    if ratio >= 2.0 or abs(z_score) >= 8.0:
        return "HIGH"
    if ratio >= 1.2 or abs(z_score) >= 3.0:
        return "MODERATE"
    return "LOW"


def run_anomaly_detection(
    normal_df: pd.DataFrame,
    target_df: pd.DataFrame,
    scenario_name: str,
    threshold_multiplier: float = DEFAULT_THRESHOLD_MULTIPLIER,
    zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD,
    enable_isolation_forest: bool = True,
    save_outputs: bool = True,
) -> DetectionSummary:
    """
    Run threshold, Z-score, and validated Isolation Forest anomaly detection
    on a target simulation DataFrame against a normal baseline DataFrame.
    """
    if normal_df.empty or target_df.empty:
        raise ValueError("Both normal_df and target_df must be non-empty DataFrames.")

    ensure_output_directories()

    normal = normal_df.copy()
    target = target_df.copy()
    normal["timestamp"] = pd.to_datetime(normal["timestamp"])
    target["timestamp"] = pd.to_datetime(target["timestamp"])

    # Elapsed minutes for startup transient handling (first 15 min)
    t0 = target["timestamp"].iloc[0]
    target["_elapsed_min"] = (target["timestamp"] - t0).dt.total_seconds() / 60.0

    # Steady-state baseline window (after first 15 min when dry-weather flow stabilizes)
    n_t0 = normal["timestamp"].iloc[0]
    normal_elapsed = (normal["timestamp"] - n_t0).dt.total_seconds() / 60.0
    normal_steady = normal[normal_elapsed >= 15.0]
    if normal_steady.empty:
        normal_steady = normal

    baselines: Dict[str, float] = {}
    node_stats: Dict[str, Dict[str, Any]] = {}
    conduit_stats: Dict[str, Dict[str, Any]] = {}
    alerts: List[Dict[str, Any]] = []

    # 1. Monitor junctions J1, J2, J3 independently
    for node_id in JUNCTION_IDS:
        col = f"{node_id}_depth_m"
        if col not in normal.columns or col not in target.columns:
            continue

        mean_val = float(normal[col].mean())
        std_val = _safe_std(normal[col], MIN_STD_FLOOR_M)
        upper_thresh = mean_val * threshold_multiplier
        baselines[col] = mean_val

        z_scores = (target[col] - mean_val) / std_val
        post_startup = target["_elapsed_min"] >= 15.0
        thresh_flag = target[col] > upper_thresh
        # Only flag negative Z-scores after initial 15-min pipe fill-up transient
        z_flag = (z_scores > zscore_threshold) | (post_startup & (z_scores < -zscore_threshold))

        target[f"{node_id}_zscore"] = z_scores
        target[f"{node_id}_threshold_anomaly"] = thresh_flag
        target[f"{node_id}_zscore_anomaly"] = z_flag
        target[f"{node_id}_anomaly"] = thresh_flag | z_flag

        node_stats[node_id] = {
            "baseline_mean_m": round(mean_val, 6),
            "baseline_std_m": round(std_val, 6),
            "upper_threshold_m": round(upper_thresh, 6),
            "threshold_exceeded_count": int(thresh_flag.sum()),
            "zscore_exceeded_count": int(z_flag.sum()),
            "combined_anomaly_count": int((thresh_flag | z_flag).sum()),
            "max_observed_depth_m": round(float(target[col].max()), 6),
            "max_zscore": round(float(z_scores.max()), 3),
        }

        flood_col = f"{node_id}_flooding_cms"
        combined_mask = thresh_flag | z_flag
        for idx in target.index[combined_mask]:
            row = target.loc[idx]
            obs = float(row[col])
            z = float(z_scores.loc[idx])
            is_flood = bool(row.get(flood_col, 0.0) > 0.0)
            ratio = obs / mean_val if mean_val > 0 else 0.0
            methods = []
            if bool(thresh_flag.loc[idx]):
                methods.append("threshold_120pct")
            if bool(z_flag.loc[idx]):
                methods.append("z_score")

            alerts.append(
                {
                    "timestamp": row["timestamp"].isoformat(),
                    "scenario": scenario_name,
                    "asset_id": node_id,
                    "asset_type": "junction",
                    "metric": "depth_m",
                    "observed_value": round(obs, 6),
                    "baseline_value": round(mean_val, 6),
                    "threshold": round(upper_thresh, 6),
                    "z_score": round(z, 3),
                    "detection_method": "+".join(methods),
                    "severity": _compute_severity(ratio, z, is_flood),
                    "suspected_condition": _infer_suspected_condition(
                        row, node_id, col, "high", baselines
                    ),
                    "disclaimer": "Hydraulic anomaly indicator only; not confirmed physical proof of fault or contamination.",
                }
            )

    # 2. Monitor conduits C1, C2, C3 (flow and velocity when available)
    for conduit_id in CONDUIT_LABELS:
        c_summary: Dict[str, Any] = {}
        for metric_suffix, floor in [("flow_cms", MIN_STD_FLOOR_FLOW_CMS), ("velocity_mps", MIN_STD_FLOOR_VEL_MPS)]:
            col = f"{conduit_id}_{metric_suffix}"
            if col not in normal.columns or col not in target.columns:
                continue

            steady_mean = float(normal_steady[col].mean())
            steady_std = _safe_std(normal_steady[col], floor)
            upper_thresh = steady_mean * 1.50  # +50% surge
            lower_thresh = steady_mean * 0.70  # -30% drop (blockage / restriction)
            baselines[col] = steady_mean

            z_scores = (target[col] - steady_mean) / steady_std
            post_startup = target["_elapsed_min"] >= 15.0

            high_flag = target[col] > upper_thresh
            low_flag = post_startup & (target[col] < lower_thresh)
            z_flag = post_startup & (z_scores.abs() > zscore_threshold)
            combined_flag = high_flag | low_flag | z_flag

            target[f"{col}_zscore"] = z_scores
            target[f"{col}_anomaly"] = combined_flag

            c_summary[metric_suffix] = {
                "steady_baseline_mean": round(steady_mean, 6),
                "steady_baseline_std": round(steady_std, 6),
                "upper_threshold": round(upper_thresh, 6),
                "lower_threshold": round(lower_thresh, 6),
                "high_count": int(high_flag.sum()),
                "low_count": int(low_flag.sum()),
                "zscore_count": int(z_flag.sum()),
                "combined_count": int(combined_flag.sum()),
                "min_observed": round(float(target[col].min()), 6),
                "max_observed": round(float(target[col].max()), 6),
            }

            for idx in target.index[combined_flag]:
                row = target.loc[idx]
                obs = float(row[col])
                z = float(z_scores.loc[idx])
                direction = "high" if obs >= steady_mean else "low"
                thresh_used = upper_thresh if direction == "high" else lower_thresh
                ratio = (obs / steady_mean) if steady_mean > 0 else 0.0
                if direction == "low" and obs > 0:
                    ratio = max(ratio, steady_mean / obs)
                methods = []
                if bool(high_flag.loc[idx]):
                    methods.append("upper_threshold_150pct")
                if bool(low_flag.loc[idx]):
                    methods.append("lower_threshold_70pct")
                if bool(z_flag.loc[idx]):
                    methods.append("z_score")

                alerts.append(
                    {
                        "timestamp": row["timestamp"].isoformat(),
                        "scenario": scenario_name,
                        "asset_id": conduit_id,
                        "asset_type": "conduit",
                        "metric": metric_suffix,
                        "observed_value": round(obs, 6),
                        "baseline_value": round(steady_mean, 6),
                        "threshold": round(thresh_used, 6),
                        "z_score": round(z, 3),
                        "detection_method": "+".join(methods),
                        "severity": _compute_severity(ratio, z, False),
                        "suspected_condition": _infer_suspected_condition(
                            row, conduit_id, metric_suffix, direction, baselines
                        ),
                        "disclaimer": "Hydraulic anomaly indicator only; not confirmed physical proof of fault or contamination.",
                    }
                )

        conduit_stats[conduit_id] = c_summary

    # 3. Optional Isolation Forest (validated against steady-state normal baseline)
    iso_validation: Dict[str, Any] = {"enabled": False, "validated": False}
    available_ml_cols = [c for c in DEFAULT_ML_FEATURES if c in normal.columns and c in target.columns]
    if enable_isolation_forest and len(available_ml_cols) >= 4 and len(normal_steady) >= 50:
        scaler = StandardScaler()
        x_train = scaler.fit_transform(normal_steady[available_ml_cols].fillna(0.0).to_numpy())
        post_mask = (target["_elapsed_min"] >= 15.0).to_numpy()
        x_target = scaler.transform(target[available_ml_cols].fillna(0.0).to_numpy())

        model = IsolationForest(
            n_estimators=100,
            contamination=0.01,
            random_state=42,
        )
        model.fit(x_train)
        train_preds = model.predict(x_train)  # -1 = anomaly, 1 = normal
        normal_fp_rate = float((train_preds == -1).mean())

        # Only accept Isolation Forest flags if false-positive rate on normal data <= 5%
        is_validated = normal_fp_rate <= 0.05
        raw_preds = model.predict(x_target)
        target_scores = model.decision_function(x_target)
        iso_flags = (raw_preds == -1) & post_mask if is_validated else np.zeros(len(target), dtype=bool)

        target["isolation_forest_score"] = target_scores
        target["isolation_forest_anomaly"] = iso_flags

        iso_validation = {
            "enabled": True,
            "validated": is_validated,
            "training_window": "post_startup_steady_state (>=15 min)",
            "features_used": available_ml_cols,
            "normal_false_positive_rate_pct": round(normal_fp_rate * 100.0, 2),
            "target_flagged_count": int(iso_flags.sum()),
            "target_flagged_pct": round(float(iso_flags.mean()) * 100.0, 2),
        }

    # Combine overall per-row anomaly flag
    anomaly_cols = [c for c in target.columns if c.endswith("_anomaly")]
    target["any_anomaly"] = target[anomaly_cols].any(axis=1) if anomaly_cols else False
    target = target.drop(columns=["_elapsed_min"], errors="ignore")

    alerts_df = pd.DataFrame(alerts)
    if not alerts_df.empty:
        alerts_df = alerts_df.sort_values(["timestamp", "asset_id", "metric"]).reset_index(drop=True)

    alerts_csv_path = ANOMALIES_OUTPUT_DIR / f"{scenario_name}_alerts.csv"
    annotated_csv_path = ANOMALIES_OUTPUT_DIR / f"{scenario_name}_annotated_readings.csv"

    if save_outputs:
        alerts_df.to_csv(alerts_csv_path, index=False)
        target.to_csv(annotated_csv_path, index=False)

    return DetectionSummary(
        scenario=scenario_name,
        total_readings=len(target),
        node_stats=node_stats,
        conduit_stats=conduit_stats,
        isolation_forest_validation=iso_validation,
        alerts_df=alerts_df,
        annotated_df=target,
        alerts_csv_path=alerts_csv_path if save_outputs else None,
    )
