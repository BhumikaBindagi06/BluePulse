"""
Centralized configuration, paths, hydraulic parameters, and scenario definitions
for the BluePulse Sewer & Sanitation Module (Member 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


# Project root: .../BluePulse
PROJECT_DIR: Path = Path(__file__).resolve().parent.parent

# Existing preserved directories
MODELS_DIR: Path = PROJECT_DIR / "sewer_module" / "models"
SCENARIO_MODELS_DIR: Path = MODELS_DIR / "scenarios"
DATA_DIR: Path = PROJECT_DIR / "data"

# Structured output directories (kept separate from existing preserved CSVs/PNGs)
OUTPUTS_DIR: Path = DATA_DIR / "outputs"
SCENARIO_DATA_DIR: Path = OUTPUTS_DIR / "simulations"
ANOMALIES_OUTPUT_DIR: Path = OUTPUTS_DIR / "anomalies"
RISK_OUTPUT_DIR: Path = OUTPUTS_DIR / "risk"
PLOTS_OUTPUT_DIR: Path = OUTPUTS_DIR / "plots"
API_EXPORTS_DIR: Path = OUTPUTS_DIR / "api_exports"

# Preserved original SWMM models (never overwritten)
NORMAL_INP_PATH: Path = MODELS_DIR / "bluepulse_sewer.inp"
BLOCKAGE_INP_PATH: Path = MODELS_DIR / "bluepulse_blockage.inp"

# Preserved original datasets (never overwritten)
LEGACY_NORMAL_CSV: Path = DATA_DIR / "normal_readings.csv"
LEGACY_BLOCKAGE_CSV: Path = DATA_DIR / "blockage_readings.csv"

# Network topology metadata matching bluepulse_sewer.inp
JUNCTION_IDS: List[str] = ["J1", "J2", "J3"]
OUTFALL_IDS: List[str] = ["O1"]
NODE_IDS: List[str] = JUNCTION_IDS + OUTFALL_IDS
SWMM_LINK_IDS: List[str] = ["1", "2", "3"]
CONDUIT_LABEL_MAP: Dict[str, str] = {"1": "C1", "2": "C2", "3": "C3"}

# Physical geometry from bluepulse_sewer.inp (SI / CMS units)
JUNCTION_MAX_DEPTH_M: Dict[str, float] = {"J1": 2.0, "J2": 2.0, "J3": 2.0}
JUNCTION_ELEVATION_M: Dict[str, float] = {"J1": 100.0, "J2": 99.0, "J3": 98.0, "O1": 97.0}
CONDUIT_LENGTH_M: Dict[str, float] = {"1": 100.0, "2": 100.0, "3": 100.0}
CONDUIT_SLOPE: Dict[str, float] = {"1": 0.01, "2": 0.01, "3": 0.01}
CONDUIT_ROUGHNESS: Dict[str, float] = {"1": 0.013, "2": 0.013, "3": 0.013}
NORMAL_CONDUIT_DIAMETER_M: Dict[str, float] = {"1": 0.30, "2": 0.30, "3": 0.30}
# All conduits connected to each junction (upstream + downstream) for SWMM surcharge crown height
JUNCTION_CONNECTED_CONDUITS: Dict[str, List[str]] = {
    "J1": ["1"],
    "J2": ["1", "2"],
    "J3": ["2", "3"],
}

# Separate corrected heavy-rainfall model path (preserves original bluepulse_heavy_rainfall.inp)
CORRECTED_HEAVY_RAINFALL_INP_PATH: Path = SCENARIO_MODELS_DIR / "bluepulse_heavy_rainfall_corrected.inp"

# Anomaly detection defaults
DEFAULT_THRESHOLD_MULTIPLIER: float = 1.20  # 120% of normal baseline (matches existing experiments)
DEFAULT_ZSCORE_THRESHOLD: float = 3.0
MIN_STD_FLOOR_M: float = 0.002  # 2 mm sensor/numerical noise floor for Z-score stability
MIN_STD_FLOOR_FLOW_CMS: float = 0.0005  # 0.5 L/s floor for Z-score stability
MIN_STD_FLOOR_VEL_MPS: float = 0.05

# Spatial and cross-contamination defaults
DEFAULT_PROXIMITY_THRESHOLDS_M: Dict[str, float] = {
    "critical": 5.0,
    "high": 15.0,
    "moderate": 30.0,
}
LOW_WATER_PRESSURE_BAR: float = 1.0  # Pressure below 1.0 bar increases intrusion susceptibility
CRITICAL_WATER_PRESSURE_BAR: float = 0.2  # Near-zero or negative transient pressure
LOW_CHLORINE_RESIDUAL_MG_L: float = 0.2  # WHO minimum free chlorine residual guideline


@dataclass(frozen=True)
class ScenarioSpec:
    """Metadata describing a SWMM simulation scenario."""

    name: str
    title: str
    inp_path: Path
    description: str
    modifications: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    is_baseline: bool = False
    conduit_diameters_m: Dict[str, float] = field(default_factory=lambda: dict(NORMAL_CONDUIT_DIAMETER_M))
    conduit_roughness: Dict[str, float] = field(default_factory=lambda: dict(CONDUIT_ROUGHNESS))


def get_scenario_specs() -> Dict[str, ScenarioSpec]:
    """Return all supported hydraulic simulation scenarios."""
    return {
        "normal": ScenarioSpec(
            name="normal",
            title="Normal Dry-Weather Baseline",
            inp_path=NORMAL_INP_PATH,
            description="Original bluepulse_sewer.inp dry-weather steady inflow (0.005 CMS at J1).",
            modifications=["None (original preserved baseline model)."],
            assumptions=[
                "Constant dry-weather inflow of 0.005 CMS (5 L/s) at upstream junction J1.",
                "All three circular conduits (C1, C2, C3) have 0.30 m diameter, 100 m length, n=0.013, 1% slope.",
                "All junctions (J1, J2, J3) have 2.0 m maximum depth; free outfall at O1.",
            ],
            is_baseline=True,
            conduit_diameters_m={"1": 0.30, "2": 0.30, "3": 0.30},
        ),
        "partial_blockage": ScenarioSpec(
            name="partial_blockage",
            title="Partial Blockage in Conduit C2 (0.30 m -> 0.15 m)",
            inp_path=BLOCKAGE_INP_PATH,
            description="Original bluepulse_blockage.inp reducing Conduit 2 diameter by 50% (75% area reduction).",
            modifications=["Conduit 2 circular diameter reduced from 0.30 m to 0.15 m."],
            assumptions=[
                "Represents sediment/grease accumulation constricting effective flow area in Conduit 2 (J2->J3).",
                "Inflow remains constant at 0.005 CMS at J1.",
            ],
            conduit_diameters_m={"1": 0.30, "2": 0.15, "3": 0.30},
        ),
        "severe_blockage": ScenarioSpec(
            name="severe_blockage",
            title="Severe Blockage in Conduit C2 (0.30 m -> 0.06 m)",
            inp_path=SCENARIO_MODELS_DIR / "bluepulse_severe_blockage.inp",
            description="Severe constriction in Conduit 2 (80% diameter reduction, 96% area loss) causing upstream surcharge/overflow.",
            modifications=[
                "Conduit 2 circular diameter reduced from 0.30 m to 0.06 m.",
                "Conduit 2 Manning roughness increased from 0.013 to 0.025 to reflect debris drag.",
            ],
            assumptions=[
                "Models near-complete obstruction (debris/root intrusion) in C2 while 0.005 CMS continues entering J1.",
                "Original network elevations, inflow, and simulation window (6 hours) remain unchanged.",
            ],
            conduit_diameters_m={"1": 0.30, "2": 0.06, "3": 0.30},
            conduit_roughness={"1": 0.013, "2": 0.025, "3": 0.013},
        ),
        "heavy_rainfall": ScenarioSpec(
            name="heavy_rainfall",
            title="Heavy Rainfall Storm Runoff & Surcharge",
            inp_path=SCENARIO_MODELS_DIR / "bluepulse_heavy_rainfall.inp",
            description="Adds a 2-hour intense storm event draining from urban subcatchments into J1 and J2.",
            modifications=[
                "Enabled Rainfall/Runoff via [RAINGAGES], [SUBCATCHMENTS], [SUBAREAS], and [TIMESERIES] STORM_TS.",
                "Added urban impervious catchments S1 (4.5 ha -> J1) and S2 (4.5 ha -> J2) with peak 60 mm/hr rainfall.",
            ],
            assumptions=[
                "Models stormwater inflow/infiltration entering a combined or storm-impacted sewer.",
                "Original conduits, slopes, elevations, and 0.005 CMS dry-weather baseflow at J1 are preserved.",
            ],
            conduit_diameters_m={"1": 0.30, "2": 0.30, "3": 0.30},
        ),
        "sudden_inflow": ScenarioSpec(
            name="sudden_inflow",
            title="Sudden Abnormal Discharge / Shock Inflow at J2",
            inp_path=SCENARIO_MODELS_DIR / "bluepulse_sudden_inflow.inp",
            description="Sudden high-volume surge injected at manhole J2 between 01:00 and 02:30 (up to 0.14 CMS).",
            modifications=[
                "Added [INFLOWS] time-series discharge SURGE_TS at J2 peaking at 0.14 CMS (140 L/s) from 01:00 to 02:30.",
            ],
            assumptions=[
                "Models sudden unauthorized industrial/tanker discharge, main break intrusion, or upstream pump dump at J2.",
                "Baseline 0.005 CMS inflow at J1 and all pipe geometries are unchanged.",
            ],
            conduit_diameters_m={"1": 0.30, "2": 0.30, "3": 0.30},
        ),
        "downstream_siltation": ScenarioSpec(
            name="downstream_siltation",
            title="Downstream Obstruction / Siltation in Conduit C3",
            inp_path=SCENARIO_MODELS_DIR / "bluepulse_downstream_siltation.inp",
            description="Conduit 3 (J3 -> O1) diameter reduced to 0.08 m with elevated roughness (0.030) to test J3 backwater.",
            modifications=[
                "Conduit 3 circular diameter reduced from 0.30 m to 0.08 m.",
                "Conduit 3 Manning roughness increased from 0.013 to 0.030.",
            ],
            assumptions=[
                "Models downstream outfall constriction or heavy sediment buildup in C3 causing backwater at J3.",
                "Dry-weather inflow at J1 remains 0.005 CMS.",
            ],
            conduit_diameters_m={"1": 0.30, "2": 0.30, "3": 0.08},
            conduit_roughness={"1": 0.013, "2": 0.013, "3": 0.030},
        ),
    }


def get_corrected_heavy_rainfall_spec() -> ScenarioSpec:
    """Return the ScenarioSpec for the separate WARNING-09-corrected heavy-rainfall model."""
    return ScenarioSpec(
        name="heavy_rainfall_corrected",
        title="Heavy Rainfall Storm Runoff & Surcharge (RG1 0:30 Corrected)",
        inp_path=CORRECTED_HEAVY_RAINFALL_INP_PATH,
        description=(
            "Separate corrected heavy-rainfall model aligning RG1 recording interval (0:30) "
            "with STORM_TS 30-minute entries to eliminate SWMM WARNING 09."
        ),
        modifications=[
            "Changed [RAINGAGES] RG1 recording interval from 0:05 to 0:30 to match STORM_TS 30-minute time steps.",
            "Preserved original subcatchments (S1, S2), Horton infiltration, STORM_TS intensities, and conduit geometry.",
        ],
        assumptions=[
            "STORM_TS entries (0:00 to 4:00 in 30-minute increments, peak 60 mm/hr) represent 30-minute block intensities.",
            "Original bluepulse_heavy_rainfall.inp and its validated outputs remain preserved separately.",
        ],
        conduit_diameters_m={"1": 0.30, "2": 0.30, "3": 0.30},
        conduit_roughness={"1": 0.013, "2": 0.013, "3": 0.013},
    )


def ensure_output_directories() -> None:
    """Create all structured output directories if they do not exist."""
    for directory in [
        SCENARIO_MODELS_DIR,
        OUTPUTS_DIR,
        SCENARIO_DATA_DIR,
        ANOMALIES_OUTPUT_DIR,
        RISK_OUTPUT_DIR,
        PLOTS_OUTPUT_DIR,
        API_EXPORTS_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
