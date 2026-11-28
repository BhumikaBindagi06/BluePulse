"""
SWMM .inp fault scenario generator for BluePulse.

Preserves the original normal model (bluepulse_sewer.inp) and existing blockage
model (bluepulse_blockage.inp) untouched, and generates separate fault-scenario
.inp files with documented engineering modifications and assumptions.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List

from sewer_module.config import (
    BLOCKAGE_INP_PATH,
    CORRECTED_HEAVY_RAINFALL_INP_PATH,
    NORMAL_INP_PATH,
    SCENARIO_MODELS_DIR,
    ensure_output_directories,
    get_scenario_specs,
)

logger = logging.getLogger(__name__)


def _replace_section_line(
    lines: List[str],
    section_header: str,
    target_prefix: str,
    replacement_line: str,
) -> List[str]:
    """Replace the first data line starting with target_prefix inside a SWMM section."""
    in_section = False
    updated: List[str] = []
    replaced = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped.upper() == section_header.upper()
            updated.append(line)
            continue

        if in_section and not replaced and stripped and not stripped.startswith(";"):
            tokens = stripped.split()
            if tokens and tokens[0] == target_prefix:
                updated.append(replacement_line)
                replaced = True
                continue

        updated.append(line)

    if not replaced:
        raise ValueError(
            f"Could not find entry '{target_prefix}' inside section {section_header}"
        )
    return updated


def _append_to_section(
    lines: List[str],
    section_header: str,
    new_lines: List[str],
) -> List[str]:
    """Append lines at the end of an existing SWMM section, or create the section."""
    updated: List[str] = []
    in_section = False
    inserted = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not inserted:
                updated.extend(new_lines)
                inserted = True
            in_section = stripped.upper() == section_header.upper()
        updated.append(line)

    if in_section and not inserted:
        updated.extend(new_lines)
        inserted = True

    if not inserted:
        updated.append("")
        updated.append(section_header)
        updated.extend(new_lines)

    return updated


def _insert_sections_before_report(
    lines: List[str],
    extra_sections: List[str],
) -> List[str]:
    """Insert new SWMM sections right before [REPORT] (or at the end if absent)."""
    updated: List[str] = []
    inserted = False
    for line in lines:
        if not inserted and line.strip().upper() == "[REPORT]":
            updated.extend(extra_sections)
            updated.append("")
            inserted = True
        updated.append(line)
    if not inserted:
        updated.append("")
        updated.extend(extra_sections)
    return updated


def _set_title(lines: List[str], note: str) -> List[str]:
    """Annotate [TITLE] with scenario note without altering hydraulic parameters."""
    updated: List[str] = []
    in_title = False
    added = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_title and not added:
                updated.append(note)
                added = True
            in_title = stripped.upper() == "[TITLE]"
        updated.append(line)
    return updated


def build_severe_blockage_inp(base_lines: List[str], output_path: Path) -> None:
    """Create severe blockage model: Conduit 2 diameter 0.30 m -> 0.06 m, n=0.025."""
    lines = _set_title(
        base_lines,
        ";;BluePulse Scenario: Severe Blockage in Conduit 2 (diameter 0.06 m, n=0.025)",
    )
    lines = _replace_section_line(
        lines,
        "[CONDUITS]",
        "2",
        "2                J2               J3               100        0.025      0          0          0          0",
    )
    lines = _replace_section_line(
        lines,
        "[XSECTIONS]",
        "2",
        "2                CIRCULAR     0.06             0          0          0          1",
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_downstream_siltation_inp(base_lines: List[str], output_path: Path) -> None:
    """Create downstream siltation/obstruction model: Conduit 3 diameter 0.30 m -> 0.08 m, n=0.030."""
    lines = _set_title(
        base_lines,
        ";;BluePulse Scenario: Downstream Siltation/Obstruction in Conduit 3 (diameter 0.08 m, n=0.030)",
    )
    lines = _replace_section_line(
        lines,
        "[CONDUITS]",
        "3",
        "3                J3               O1               100        0.030      0          0          0          0",
    )
    lines = _replace_section_line(
        lines,
        "[XSECTIONS]",
        "3",
        "3                CIRCULAR     0.08             0          0          0          1",
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_heavy_rainfall_lines(
    base_lines: List[str],
    rain_interval: str,
    title_note: str,
) -> List[str]:
    """Assemble heavy-rainfall SWMM lines with the specified RG1 recording interval."""
    lines = _set_title(base_lines, title_note)
    rain_sections = [
        "",
        "[RAINGAGES]",
        ";;Name           Format    Interval SCF      Source",
        f"RG1              INTENSITY {rain_interval:<8} 1.0      TIMESERIES STORM_TS",
        "",
        "[SUBCATCHMENTS]",
        ";;Name           Rain Gage        Outlet           Area     %Imperv  Width    %Slope   CurbLen  SnowPack",
        "S1               RG1              J1               4.5      85       150      1.0      0",
        "S2               RG1              J2               4.5      85       150      1.0      0",
        "",
        "[SUBAREAS]",
        ";;Subcatchment   N-Imperv   N-Perv     S-Imperv   S-Perv     PctZero    RouteTo    PctRouted",
        "S1               0.012      0.10       1.5        3.0        25         OUTLET",
        "S2               0.012      0.10       1.5        3.0        25         OUTLET",
        "",
        "[INFILTRATION]",
        ";;Subcatchment   MaxRate    MinRate    Decay      DryTime    MaxInfil",
        "S1               76.2       3.81       4.0        7          0",
        "S2               76.2       3.81       4.0        7          0",
        "",
        "[TIMESERIES]",
        ";;Name           Date       Time       Value",
        "STORM_TS                    0:00       0.0",
        "STORM_TS                    0:30       5.0",
        "STORM_TS                    1:00       20.0",
        "STORM_TS                    1:30       45.0",
        "STORM_TS                    2:00       60.0",
        "STORM_TS                    2:30       50.0",
        "STORM_TS                    3:00       25.0",
        "STORM_TS                    3:30       8.0",
        "STORM_TS                    4:00       0.0",
        "STORM_TS                    6:00       0.0",
    ]
    return _insert_sections_before_report(lines, rain_sections)


def build_heavy_rainfall_inp(base_lines: List[str], output_path: Path) -> None:
    """Create heavy rainfall runoff model with urban subcatchments draining to J1 and J2."""
    lines = _build_heavy_rainfall_lines(
        base_lines,
        rain_interval="0:05",
        title_note=";;BluePulse Scenario: Heavy Rainfall Storm Event (peak 60 mm/hr draining to J1 and J2)",
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_heavy_rainfall_corrected_inp(base_lines: List[str], output_path: Path) -> None:
    """Create WARNING-09-corrected heavy rainfall model with RG1 interval 0:30 matching STORM_TS."""
    lines = _build_heavy_rainfall_lines(
        base_lines,
        rain_interval="0:30",
        title_note=";;BluePulse Scenario: Heavy Rainfall Storm Event Corrected (RG1 0:30 matching STORM_TS)",
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_sudden_inflow_inp(base_lines: List[str], output_path: Path) -> None:
    """Create sudden abnormal discharge/shock inflow model injecting a surge at J2."""
    lines = _set_title(
        base_lines,
        ";;BluePulse Scenario: Sudden Abnormal Discharge at J2 (peak 0.14 CMS from 01:00 to 02:30)",
    )
    lines = _append_to_section(
        lines,
        "[INFLOWS]",
        [
            "J2               FLOW             SURGE_TS         FLOW     1.0      1.0      0.0",
        ],
    )
    surge_section = [
        "",
        "[TIMESERIES]",
        ";;Name           Date       Time       Value",
        "SURGE_TS                    0:00       0.000",
        "SURGE_TS                    0:55       0.000",
        "SURGE_TS                    1:00       0.060",
        "SURGE_TS                    1:15       0.120",
        "SURGE_TS                    1:30       0.140",
        "SURGE_TS                    2:00       0.110",
        "SURGE_TS                    2:30       0.040",
        "SURGE_TS                    2:45       0.000",
        "SURGE_TS                    6:00       0.000",
    ]
    lines = _insert_sections_before_report(lines, surge_section)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_all_scenario_models(force: bool = False) -> Dict[str, Path]:
    """
    Generate all separate fault-scenario SWMM .inp files from bluepulse_sewer.inp.
    Original bluepulse_sewer.inp and bluepulse_blockage.inp are never modified.
    """
    ensure_output_directories()

    if not NORMAL_INP_PATH.exists():
        raise FileNotFoundError(f"Original normal SWMM model not found: {NORMAL_INP_PATH}")
    if not BLOCKAGE_INP_PATH.exists():
        raise FileNotFoundError(f"Original blockage SWMM model not found: {BLOCKAGE_INP_PATH}")

    base_lines = NORMAL_INP_PATH.read_text(encoding="utf-8").splitlines()
    specs = get_scenario_specs()

    builders = {
        "severe_blockage": build_severe_blockage_inp,
        "heavy_rainfall": build_heavy_rainfall_inp,
        "sudden_inflow": build_sudden_inflow_inp,
        "downstream_siltation": build_downstream_siltation_inp,
    }

    paths: Dict[str, Path] = {}
    metadata: Dict[str, dict] = {}

    for name, spec in specs.items():
        if name in builders:
            if force or not spec.inp_path.exists():
                builders[name](base_lines, spec.inp_path)
                logger.info("Generated scenario model: %s -> %s", name, spec.inp_path)
        paths[name] = spec.inp_path
        metadata[name] = {
            "name": spec.name,
            "title": spec.title,
            "inp_path": str(spec.inp_path),
            "description": spec.description,
            "modifications": spec.modifications,
            "assumptions": spec.assumptions,
            "is_baseline": spec.is_baseline,
            "conduit_diameters_m": spec.conduit_diameters_m,
        }

    meta_path = SCENARIO_MODELS_DIR / "scenario_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return paths


def generate_corrected_heavy_rainfall_model(force: bool = False) -> Path:
    """
    Generate the separate WARNING-09-corrected heavy rainfall SWMM .inp file
    without altering bluepulse_sewer.inp or the original bluepulse_heavy_rainfall.inp.
    """
    ensure_output_directories()
    if not NORMAL_INP_PATH.exists():
        raise FileNotFoundError(f"Original normal SWMM model not found: {NORMAL_INP_PATH}")

    if force or not CORRECTED_HEAVY_RAINFALL_INP_PATH.exists():
        base_lines = NORMAL_INP_PATH.read_text(encoding="utf-8").splitlines()
        build_heavy_rainfall_corrected_inp(base_lines, CORRECTED_HEAVY_RAINFALL_INP_PATH)
        logger.info(
            "Generated corrected heavy-rainfall model: %s",
            CORRECTED_HEAVY_RAINFALL_INP_PATH,
        )
    return CORRECTED_HEAVY_RAINFALL_INP_PATH
