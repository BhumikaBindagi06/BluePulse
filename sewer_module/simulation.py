"""
Hydraulic simulation runner and SWMM output/report extractor for BluePulse.

Uses PySWMM Simulation for 10-second routing-step telemetry, PySWMM Output
(SWMM binary .out reader) for verified SWMM report-step velocity, capacity,
rainfall, and flooding losses, and parses the SWMM .rpt summary.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from pyswmm import Links, Nodes, Output, Simulation
from swmm.toolkit.shared_enum import LinkAttribute, NodeAttribute, SystemAttribute

from sewer_module.config import (
    CONDUIT_LABEL_MAP,
    CONDUIT_LENGTH_M,
    CONDUIT_SLOPE,
    JUNCTION_IDS,
    JUNCTION_MAX_DEPTH_M,
    NODE_IDS,
    SCENARIO_DATA_DIR,
    SCENARIO_MODELS_DIR,
    SWMM_LINK_IDS,
    ScenarioSpec,
    ensure_output_directories,
    get_corrected_heavy_rainfall_spec,
    get_scenario_specs,
)
from sewer_module.inp_builder import (
    generate_all_scenario_models,
    generate_corrected_heavy_rainfall_model,
)

logger = logging.getLogger(__name__)


@dataclass
class SimulationRunResult:
    """Container for outputs produced by a single SWMM scenario run."""

    scenario: str
    step_df: pd.DataFrame
    report_df: pd.DataFrame
    rpt_summary: Dict[str, Any]
    step_csv_path: Path
    report_csv_path: Path
    rpt_path: Path
    out_path: Path


def manning_full_flow_cms(diameter_m: float, slope: float = 0.01, n: float = 0.013) -> float:
    """
    Calculate circular pipe full-flow capacity Q_full (CMS) via Manning's equation.

    Q_full = (1 / n) * A * R_h^(2/3) * S^(1/2), where for a full circular pipe:
      A = pi * D^2 / 4, R_h = D / 4.
    """
    area = math.pi * (diameter_m ** 2) / 4.0
    hydraulic_radius = diameter_m / 4.0
    return (1.0 / n) * area * (hydraulic_radius ** (2.0 / 3.0)) * math.sqrt(slope)


def parse_rpt_summary(rpt_path: Path) -> Dict[str, Any]:
    """Parse key engineering diagnostics from an EPA SWMM .rpt file."""
    if not rpt_path.exists():
        return {"error": f"Report file not found: {rpt_path}"}

    lines = rpt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    summary: Dict[str, Any] = {
        "continuity_error_pct": None,
        "runoff_continuity_error_pct": None,
        "total_precipitation_mm": None,
        "warnings": [line.strip() for line in lines if "WARNING " in line],
        "surcharged_nodes": [],
        "flooded_nodes": [],
        "surcharged_conduits": [],
        "node_depth_summary": {},
        "link_flow_summary": {},
    }

    # Split .rpt into named sections delimited by SWMM's "***" header bars
    sections: Dict[str, List[str]] = {}
    current_section: Optional[str] = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if (
            i + 2 < len(lines)
            and set(line) == {"*"}
            and len(line) >= 5
            and set(lines[i + 2].strip()) == {"*"}
        ):
            current_section = lines[i + 1].strip()
            sections[current_section] = []
            i += 3
            continue
        if current_section is not None:
            sections[current_section].append(lines[i])
        i += 1

    full_text = "\n".join(lines)
    flow_match = re.search(
        r"Flow Routing Continuity.*?Continuity Error \(%\)\s*\.+\s*([-\d.]+)",
        full_text,
        re.DOTALL,
    )
    if flow_match:
        summary["continuity_error_pct"] = float(flow_match.group(1))

    runoff_match = re.search(
        r"Runoff Quantity Continuity.*?Continuity Error \(%\)\s*\.+\s*([-\d.]+)",
        full_text,
        re.DOTALL,
    )
    if runoff_match:
        summary["runoff_continuity_error_pct"] = float(runoff_match.group(1))

    precip_match = re.search(
        r"Total Precipitation\s*\.+\s*[\d.]+\s+([\d.]+)",
        full_text,
    )
    if precip_match:
        summary["total_precipitation_mm"] = float(precip_match.group(1))

    for sec_line in sections.get("Node Surcharge Summary", []):
        parts = sec_line.split()
        if len(parts) >= 5 and parts[0] in NODE_IDS:
            summary["surcharged_nodes"].append(
                {
                    "node_id": parts[0],
                    "type": parts[1],
                    "hours_surcharged": float(parts[2]),
                    "max_height_above_crown_m": float(parts[3]),
                    "min_depth_below_rim_m": float(parts[4]),
                }
            )

    for sec_line in sections.get("Node Flooding Summary", []):
        parts = sec_line.split()
        if len(parts) >= 7 and parts[0] in NODE_IDS:
            summary["flooded_nodes"].append(
                {
                    "node_id": parts[0],
                    "hours_flooded": float(parts[1]),
                    "max_rate_cms": float(parts[2]),
                    "total_flood_volume_10e6_ltr": float(parts[5]),
                    "max_ponded_depth_m": float(parts[6]),
                }
            )

    for sec_line in sections.get("Node Depth Summary", []):
        parts = sec_line.split()
        if len(parts) >= 8 and parts[0] in NODE_IDS:
            summary["node_depth_summary"][parts[0]] = {
                "type": parts[1],
                "avg_depth_m": float(parts[2]),
                "max_depth_m": float(parts[3]),
                "max_hgl_m": float(parts[4]),
                "reported_max_depth_m": float(parts[7]),
            }

    for sec_line in sections.get("Link Flow Summary", []):
        parts = sec_line.split()
        if len(parts) >= 8 and parts[0] in SWMM_LINK_IDS:
            label = CONDUIT_LABEL_MAP[parts[0]]
            summary["link_flow_summary"][label] = {
                "swmm_id": parts[0],
                "max_flow_cms": float(parts[2]),
                "max_velocity_mps": float(parts[5]),
                "max_full_flow_ratio": float(parts[6]),
                "max_full_depth_ratio": float(parts[7]),
            }

    for sec_line in sections.get("Conduit Surcharge Summary", []):
        parts = sec_line.split()
        if len(parts) >= 6 and parts[0] in SWMM_LINK_IDS:
            summary["surcharged_conduits"].append(
                {
                    "conduit_id": CONDUIT_LABEL_MAP[parts[0]],
                    "hours_full_both_ends": float(parts[1]),
                    "hours_full_upstream": float(parts[2]),
                    "hours_full_downstream": float(parts[3]),
                    "hours_above_normal_flow": float(parts[4]),
                    "hours_capacity_limited": float(parts[5]),
                }
            )

    return summary


def _extract_output_series(out_path: Path, spec: ScenarioSpec) -> pd.DataFrame:
    """
    Extract verified report-step time series from SWMM binary .out file using
    pyswmm.Output (FLOW_VELOCITY, CAPACITY, FLOODING_LOSSES, RAINFALL, etc.).
    """
    out = Output(str(out_path))
    out.open()
    try:
        times = list(out.times)
        if not times:
            return pd.DataFrame()

        data: Dict[str, List[Any]] = {"timestamp": times}

        # System-level rainfall & flooding
        rainfall_series = out.system_series(SystemAttribute.RAINFALL)
        runoff_series = out.system_series(SystemAttribute.RUNOFF_FLOW)
        sys_flood_series = out.system_series(SystemAttribute.FLOOD_LOSSES)
        outfall_series = out.system_series(SystemAttribute.OUTFALL_FLOWS)

        data["system_rainfall_mm_hr"] = [rainfall_series[t] for t in times]
        data["system_runoff_cms"] = [runoff_series[t] for t in times]
        data["system_flood_losses_cms"] = [sys_flood_series[t] for t in times]
        data["system_outfall_cms"] = [outfall_series[t] for t in times]

        # Node attributes
        for node_id in NODE_IDS:
            depth_s = out.node_series(node_id, NodeAttribute.INVERT_DEPTH)
            head_s = out.node_series(node_id, NodeAttribute.HYDRAULIC_HEAD)
            inflow_s = out.node_series(node_id, NodeAttribute.TOTAL_INFLOW)
            flood_s = out.node_series(node_id, NodeAttribute.FLOODING_LOSSES)

            data[f"{node_id}_depth_m"] = [depth_s[t] for t in times]
            data[f"{node_id}_head_m"] = [head_s[t] for t in times]
            data[f"{node_id}_inflow_cms"] = [inflow_s[t] for t in times]
            data[f"{node_id}_flooding_cms"] = [flood_s[t] for t in times]

        # Link attributes (native SWMM FLOW_VELOCITY and CAPACITY!)
        for link_id in SWMM_LINK_IDS:
            label = CONDUIT_LABEL_MAP[link_id]
            flow_s = out.link_series(link_id, LinkAttribute.FLOW_RATE)
            depth_s = out.link_series(link_id, LinkAttribute.FLOW_DEPTH)
            vel_s = out.link_series(link_id, LinkAttribute.FLOW_VELOCITY)
            cap_s = out.link_series(link_id, LinkAttribute.CAPACITY)

            data[f"{label}_flow_cms"] = [flow_s[t] for t in times]
            data[f"{label}_depth_m"] = [depth_s[t] for t in times]
            data[f"{label}_velocity_mps"] = [vel_s[t] for t in times]
            data[f"{label}_capacity_ratio"] = [cap_s[t] for t in times]

        df = pd.DataFrame(data)
        df["scenario"] = spec.name
        return df
    finally:
        out.close()


def _prepare_isolated_inp(spec: ScenarioSpec) -> Path:
    """
    For baseline preserved models (normal, partial_blockage), copy the .inp into
    the scenarios directory before running so the original .out/.rpt files in
    sewer_module/models/ remain untouched.
    """
    if not spec.inp_path.exists():
        raise FileNotFoundError(f"SWMM .inp file not found: {spec.inp_path}")

    if spec.inp_path.parent == SCENARIO_MODELS_DIR:
        return spec.inp_path

    isolated_path = SCENARIO_MODELS_DIR / f"_run_{spec.name}.inp"
    shutil.copy2(spec.inp_path, isolated_path)
    return isolated_path


def _execute_spec(spec: ScenarioSpec, save_outputs: bool = True) -> SimulationRunResult:
    """Execute a ScenarioSpec via PySWMM and extract step and report outputs."""
    run_inp_path = _prepare_isolated_inp(spec)
    rpt_path = run_inp_path.with_suffix(".rpt")
    out_path = run_inp_path.with_suffix(".out")

    logger.info("Running SWMM scenario '%s' from %s", spec.name, run_inp_path)

    step_records: List[Dict[str, Any]] = []
    full_flows = {
        link_id: manning_full_flow_cms(
            diameter_m=spec.conduit_diameters_m[link_id],
            slope=CONDUIT_SLOPE[link_id],
            n=spec.conduit_roughness[link_id],
        )
        for link_id in SWMM_LINK_IDS
    }

    with Simulation(str(run_inp_path)) as sim:
        nodes = Nodes(sim)
        links = Links(sim)
        node_objs = {nid: nodes[nid] for nid in NODE_IDS}
        link_objs = {lid: links[lid] for lid in SWMM_LINK_IDS}

        for _ in sim:
            row: Dict[str, Any] = {
                "timestamp": sim.current_time,
                "scenario": spec.name,
            }

            for nid, node in node_objs.items():
                depth = float(node.depth)
                row[f"{nid}_depth_m"] = depth
                row[f"{nid}_head_m"] = float(node.head)
                row[f"{nid}_total_inflow_cms"] = float(node.total_inflow)
                if nid in JUNCTION_IDS:
                    max_d = JUNCTION_MAX_DEPTH_M[nid]
                    row[f"{nid}_flooding_cms"] = float(node.flooding)
                    row[f"{nid}_depth_ratio"] = depth / max_d if max_d > 0 else 0.0

            for lid, link in link_objs.items():
                label = CONDUIT_LABEL_MAP[lid]
                flow = float(link.flow)
                depth = float(link.depth)
                volume = float(link.volume)
                length = CONDUIT_LENGTH_M[lid]
                diameter = spec.conduit_diameters_m[lid]

                # Hydraulic mean velocity Q / A_mean where A_mean = V / L (verified against SWMM .out FLOW_VELOCITY)
                mean_area = volume / length if length > 0 else 0.0
                velocity = flow / mean_area if mean_area > 1e-6 else 0.0

                row[f"{label}_flow_cms"] = flow
                row[f"{label}_depth_m"] = depth
                row[f"{label}_velocity_mps"] = velocity
                row[f"{label}_froude"] = float(link.froude)
                row[f"{label}_depth_ratio"] = depth / diameter if diameter > 0 else 0.0
                row[f"{label}_flow_capacity_ratio"] = (
                    abs(flow) / full_flows[lid] if full_flows[lid] > 0 else 0.0
                )

            step_records.append(row)

    step_df = pd.DataFrame(step_records)
    report_df = _extract_output_series(out_path, spec)
    rpt_summary = parse_rpt_summary(rpt_path)

    step_csv_path = SCENARIO_DATA_DIR / f"{spec.name}_step_readings.csv"
    report_csv_path = SCENARIO_DATA_DIR / f"{spec.name}_report_series.csv"

    if save_outputs:
        step_df.to_csv(step_csv_path, index=False)
        report_df.to_csv(report_csv_path, index=False)
        logger.info(
            "Saved scenario '%s' step readings (%d rows) and report series (%d rows)",
            spec.name,
            len(step_df),
            len(report_df),
        )

    return SimulationRunResult(
        scenario=spec.name,
        step_df=step_df,
        report_df=report_df,
        rpt_summary=rpt_summary,
        step_csv_path=step_csv_path,
        report_csv_path=report_csv_path,
        rpt_path=rpt_path,
        out_path=out_path,
    )


def run_scenario(scenario_name: str, save_outputs: bool = True) -> SimulationRunResult:
    """
    Execute an EPA SWMM simulation scenario via PySWMM and extract both
    10-second routing-step readings and 5-minute verified .out report series.
    """
    ensure_output_directories()
    generate_all_scenario_models(force=False)

    specs = get_scenario_specs()
    if scenario_name not in specs:
        raise ValueError(
            f"Unknown scenario '{scenario_name}'. Available: {sorted(specs.keys())}"
        )

    return _execute_spec(specs[scenario_name], save_outputs=save_outputs)


def run_corrected_heavy_rainfall(save_outputs: bool = True) -> SimulationRunResult:
    """
    Execute the separate WARNING-09-corrected heavy-rainfall scenario without
    modifying the original bluepulse_heavy_rainfall.inp or its validated outputs.
    """
    ensure_output_directories()
    generate_corrected_heavy_rainfall_model(force=False)
    return _execute_spec(get_corrected_heavy_rainfall_spec(), save_outputs=save_outputs)


def run_all_scenarios() -> Dict[str, SimulationRunResult]:
    """Run all registered SWMM scenarios and return their results."""
    specs = get_scenario_specs()
    results: Dict[str, SimulationRunResult] = {}
    for name in specs:
        results[name] = run_scenario(name, save_outputs=True)
    return results
