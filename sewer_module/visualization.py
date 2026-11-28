"""
Non-interactive Matplotlib visualizations for BluePulse sewer scenarios.

Preserves original PNGs in data/ and saves comprehensive multi-scenario
hydraulic, velocity, anomaly, and overflow-risk charts to data/outputs/plots/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib

matplotlib.use("Agg")  # Safe non-interactive backend for Windows CLI / servers
import matplotlib.pyplot as plt
import pandas as pd

from sewer_module.config import PLOTS_OUTPUT_DIR, ensure_output_directories


def _elapsed_minutes(df: pd.DataFrame) -> pd.Series:
    ts = pd.to_datetime(df["timestamp"])
    return (ts - ts.iloc[0]).dt.total_seconds() / 60.0


def plot_multi_scenario_j2_depth(
    scenario_dfs: Dict[str, pd.DataFrame],
    output_path: Path | None = None,
) -> Path:
    """Compare manhole J2 water depth across normal and fault scenarios."""
    ensure_output_directories()
    out = output_path or (PLOTS_OUTPUT_DIR / "scenarios_j2_depth_comparison.png")

    plt.figure(figsize=(12, 6))
    for name, df in scenario_dfs.items():
        if "J2_depth_m" in df.columns:
            plt.plot(_elapsed_minutes(df), df["J2_depth_m"], label=name, linewidth=1.8)

    plt.axhline(2.0, color="red", linestyle=":", linewidth=1.5, label="Manhole Rim / Max Depth (2.0 m)")
    plt.axhline(0.30, color="orange", linestyle="--", linewidth=1.2, label="Normal Pipe Crown (0.30 m)")
    plt.xlabel("Elapsed Simulation Time (minutes)")
    plt.ylabel("Water Depth at J2 (m)")
    plt.title("BluePulse Sewer Network - Manhole J2 Water Depth Across Scenarios")
    plt.legend(loc="best", fontsize=9)
    plt.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    return out


def plot_multi_scenario_c2_velocity_and_flow(
    scenario_dfs: Dict[str, pd.DataFrame],
    output_path: Path | None = None,
) -> Path:
    """Compare Conduit C2 flow (CMS) and verified hydraulic velocity (m/s) across scenarios."""
    ensure_output_directories()
    out = output_path or (PLOTS_OUTPUT_DIR / "scenarios_c2_flow_velocity.png")

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for name, df in scenario_dfs.items():
        mins = _elapsed_minutes(df)
        if "C2_flow_cms" in df.columns:
            axes[0].plot(mins, df["C2_flow_cms"], label=name, linewidth=1.6)
        if "C2_velocity_mps" in df.columns:
            axes[1].plot(mins, df["C2_velocity_mps"], label=name, linewidth=1.6)

    axes[0].set_ylabel("Flow in C2 (CMS)")
    axes[0].set_title("BluePulse Sewer Network - Conduit C2 Flow & Velocity Comparison")
    axes[0].legend(loc="best", fontsize=8)
    axes[0].grid(True, alpha=0.35)

    axes[1].set_xlabel("Elapsed Simulation Time (minutes)")
    axes[1].set_ylabel("Velocity in C2 (m/s)")
    axes[1].legend(loc="best", fontsize=8)
    axes[1].grid(True, alpha=0.35)

    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    return out


def plot_overflow_risk_timeline(
    risk_dfs: Dict[str, pd.DataFrame],
    output_path: Path | None = None,
) -> Path:
    """Plot peak network overflow risk score (0-100) over time per scenario."""
    ensure_output_directories()
    out = output_path or (PLOTS_OUTPUT_DIR / "scenarios_overflow_risk_timeline.png")

    plt.figure(figsize=(12, 6))
    for name, rdf in risk_dfs.items():
        if rdf.empty:
            continue
        grouped = rdf.groupby("timestamp", as_index=False)["risk_score"].max()
        grouped["timestamp"] = pd.to_datetime(grouped["timestamp"])
        mins = (grouped["timestamp"] - grouped["timestamp"].iloc[0]).dt.total_seconds() / 60.0
        plt.plot(mins, grouped["risk_score"], label=name, linewidth=1.8)

    plt.axhline(75, color="red", linestyle=":", linewidth=1.2, label="Critical Tier (75)")
    plt.axhline(50, color="orange", linestyle="--", linewidth=1.2, label="High Tier (50)")
    plt.xlabel("Elapsed Simulation Time (minutes)")
    plt.ylabel("Max Network Overflow Risk Score (0-100)")
    plt.title("BluePulse Sewer Network - Explainable Overflow Risk Timeline")
    plt.ylim(0, 105)
    plt.legend(loc="best", fontsize=9)
    plt.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    return out


def plot_scenario_junction_depths(
    scenario_name: str,
    df: pd.DataFrame,
    output_path: Path | None = None,
) -> Path:
    """Plot J1, J2, J3 water depths for an individual scenario."""
    ensure_output_directories()
    out = output_path or (PLOTS_OUTPUT_DIR / f"{scenario_name}_junction_depths.png")

    mins = _elapsed_minutes(df)
    plt.figure(figsize=(11, 5))
    for node in ["J1", "J2", "J3"]:
        col = f"{node}_depth_m"
        if col in df.columns:
            plt.plot(mins, df[col], label=node, linewidth=1.7)

    plt.xlabel("Elapsed Simulation Time (minutes)")
    plt.ylabel("Manhole Water Depth (m)")
    plt.title(f"BluePulse Scenario '{scenario_name}' - Manhole Water Depths")
    plt.legend()
    plt.grid(True, alpha=0.35)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    return out
