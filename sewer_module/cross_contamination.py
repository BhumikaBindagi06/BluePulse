"""
Potential cross-contamination risk indicator for BluePulse.

Combines:
- Member 3: Sewer overflow / surcharge / leak risk events
- Member 1: Spatial proximity (meters) and drinking-water pipe pressure (bar)
- Member 2: Water quality indicators (chlorine residual mg/L, turbidity NTU)

Never labels any result as confirmed contamination without physical/laboratory
evidence; always reports missing inputs, uncertainty, and investigation priority.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sewer_module.config import (
    CRITICAL_WATER_PRESSURE_BAR,
    DEFAULT_PROXIMITY_THRESHOLDS_M,
    LOW_CHLORINE_RESIDUAL_MG_L,
    LOW_WATER_PRESSURE_BAR,
)


def assess_potential_cross_contamination(
    sewer_asset_id: str,
    timestamp: str,
    sewer_hydraulic_state: str,
    sewer_risk_score: float,
    distance_to_water_pipe_m: Optional[float] = None,
    nearest_water_pipe_id: Optional[str] = None,
    water_pressure_bar: Optional[float] = None,
    chlorine_residual_mg_l: Optional[float] = None,
    turbidity_ntu: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluate potential cross-contamination investigation priority using transparent
    rule-based logic while explicitly tracking missing team inputs and uncertainty.

    Weights when all inputs are present (max 100):
      - Sewer hazard severity (Member 3): up to 35 pts
      - Spatial proximity (Member 1): up to 25 pts
      - Drinking-water low/negative pressure intrusion risk (Member 1): up to 20 pts
      - Chlorine residual depletion / turbidity anomaly (Member 2): up to 20 pts
    """
    available_inputs: List[str] = ["sewer_hydraulic_state", "sewer_risk_score"]
    missing_inputs: List[str] = []
    reasons: List[str] = []

    # 1. Sewer hazard component (Member 3, max 35 pts)
    state_upper = sewer_hydraulic_state.upper()
    if state_upper in ("FLOODING_SIMULATED", "CONFIRMED_OVERFLOW"):
        sewer_pts = 35.0
        reasons.append(f"Sewer asset {sewer_asset_id} is in state {state_upper}.")
    elif state_upper == "SURCHARGED":
        sewer_pts = 25.0
        reasons.append(f"Sewer asset {sewer_asset_id} is surcharged above pipe crown.")
    elif state_upper == "ANOMALY_ONLY":
        sewer_pts = 15.0 * min(1.0, max(0.0, sewer_risk_score / 50.0))
        reasons.append(f"Sewer asset {sewer_asset_id} shows a hydraulic anomaly (no surcharge).")
    else:
        sewer_pts = 0.0

    # 2. Proximity component (Member 1, max 25 pts)
    if distance_to_water_pipe_m is None:
        missing_inputs.append("Member 1: distance_to_water_pipe_m (spatial proximity)")
        prox_pts = 0.0
    else:
        available_inputs.append("distance_to_water_pipe_m")
        if distance_to_water_pipe_m <= DEFAULT_PROXIMITY_THRESHOLDS_M["critical"]:
            prox_pts = 25.0
            reasons.append(f"Water pipe within critical proximity ({distance_to_water_pipe_m:.2f} m <= 5 m).")
        elif distance_to_water_pipe_m <= DEFAULT_PROXIMITY_THRESHOLDS_M["high"]:
            prox_pts = 18.0
            reasons.append(f"Water pipe within high proximity ({distance_to_water_pipe_m:.2f} m <= 15 m).")
        elif distance_to_water_pipe_m <= DEFAULT_PROXIMITY_THRESHOLDS_M["moderate"]:
            prox_pts = 10.0
            reasons.append(f"Water pipe within moderate proximity ({distance_to_water_pipe_m:.2f} m <= 30 m).")
        else:
            prox_pts = 0.0

    # 3. Drinking-water pressure intrusion component (Member 1, max 20 pts)
    if water_pressure_bar is None:
        missing_inputs.append("Member 1: water_pressure_bar (drinking-water line pressure)")
        pressure_pts = 0.0
    else:
        available_inputs.append("water_pressure_bar")
        if water_pressure_bar <= CRITICAL_WATER_PRESSURE_BAR:
            pressure_pts = 20.0
            reasons.append(f"Critical low/negative water pressure ({water_pressure_bar:.2f} bar) permits intrusion.")
        elif water_pressure_bar < LOW_WATER_PRESSURE_BAR:
            pressure_pts = 12.0
            reasons.append(f"Reduced water pressure ({water_pressure_bar:.2f} bar < 1.0 bar).")
        else:
            pressure_pts = 0.0

    # 4. Water quality residual component (Member 2, max 20 pts)
    wq_pts = 0.0
    if chlorine_residual_mg_l is None:
        missing_inputs.append("Member 2: chlorine_residual_mg_l")
    else:
        available_inputs.append("chlorine_residual_mg_l")
        if chlorine_residual_mg_l < LOW_CHLORINE_RESIDUAL_MG_L:
            wq_pts += 12.0
            reasons.append(
                f"Low free chlorine residual ({chlorine_residual_mg_l:.2f} mg/L < {LOW_CHLORINE_RESIDUAL_MG_L} mg/L)."
            )

    if turbidity_ntu is None:
        missing_inputs.append("Member 2: turbidity_ntu")
    else:
        available_inputs.append("turbidity_ntu")
        if turbidity_ntu > 5.0:
            wq_pts += 8.0
            reasons.append(f"Elevated turbidity ({turbidity_ntu:.2f} NTU > 5.0 NTU).")
        elif turbidity_ntu > 1.0:
            wq_pts += 4.0
            reasons.append(f"Moderately elevated turbidity ({turbidity_ntu:.2f} NTU > 1.0 NTU).")

    total_score = round(min(100.0, sewer_pts + prox_pts + pressure_pts + wq_pts), 2)

    # Uncertainty & completeness calculation (5 total external inputs + sewer hazard)
    external_present = 4 - sum(
        x is None
        for x in [
            distance_to_water_pipe_m,
            water_pressure_bar,
            chlorine_residual_mg_l,
            turbidity_ntu,
        ]
    )
    completeness_ratio = (1 + external_present) / 5.0  # 1 sewer + 4 external

    if external_present == 0:
        uncertainty_level = "HIGH"
    elif external_present <= 2:
        uncertainty_level = "MODERATE"
    else:
        uncertainty_level = "LOW"

    if external_present == 0:
        priority = "INDETERMINATE_AWAITING_TEAM_INPUTS"
    elif total_score >= 70.0:
        priority = "CRITICAL_INVESTIGATION_PRIORITY"
    elif total_score >= 45.0:
        priority = "HIGH_INVESTIGATION_PRIORITY"
    elif total_score >= 20.0:
        priority = "MODERATE_INVESTIGATION_PRIORITY"
    else:
        priority = "LOW_INVESTIGATION_PRIORITY"

    return {
        "timestamp": timestamp,
        "sewer_asset_id": sewer_asset_id,
        "nearest_water_pipe_id": nearest_water_pipe_id,
        "status_label": (
            "INSUFFICIENT_DATA_AWAITING_TEAM_INPUTS"
            if external_present == 0
            else "POTENTIAL_RISK_INVESTIGATION_ONLY"
        ),
        "potential_risk_score": total_score,
        "investigation_priority": priority,
        "uncertainty_level": uncertainty_level,
        "input_completeness_pct": round(completeness_ratio * 100.0, 1),
        "score_breakdown": {
            "sewer_hazard_pts": round(sewer_pts, 2),
            "spatial_proximity_pts": round(prox_pts, 2),
            "water_pressure_pts": round(pressure_pts, 2),
            "water_quality_pts": round(wq_pts, 2),
        },
        "available_inputs": available_inputs,
        "missing_inputs": missing_inputs,
        "contributing_factors": reasons,
        "disclaimer": (
            "This indicator identifies POTENTIAL cross-contamination risk and field investigation "
            "priority only. It never proves actual drinking-water contamination without physical "
            "inspection and laboratory confirmation."
        ),
    }
