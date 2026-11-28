"""
Spatial proximity analysis between BluePulse sewer pipes/manholes and
Member 1's drinking-water distribution pipelines using GeoPandas and Shapely.

Key engineering safeguards:
1. Validates Coordinate Reference Systems (CRS) before any distance calculation.
2. Never computes Euclidean distances directly in latitude/longitude degrees.
3. Automatically reprojects geographic CRSs (e.g., EPSG:4326) to a suitable metric
   projected CRS (UTM) before calling distance calculations.
4. Explicitly flags when bluepulse_sewer.inp uses schematic (Units None) local
   coordinates and never fabricates Member 1 drinking-water pipeline geometries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import LineString, Point, shape

from sewer_module.config import (
    CONDUIT_LABEL_MAP,
    DEFAULT_PROXIMITY_THRESHOLDS_M,
    NORMAL_INP_PATH,
)

logger = logging.getLogger(__name__)


def parse_sewer_coordinates_from_inp(inp_path: Path = NORMAL_INP_PATH) -> Dict[str, Any]:
    """
    Read [MAP] units and [COORDINATES] from bluepulse_sewer.inp.
    Returns node coordinates and whether the .inp uses schematic 'Units None'.
    """
    lines = inp_path.read_text(encoding="utf-8").splitlines()
    map_units = "None"
    coords: Dict[str, Tuple[float, float]] = {}
    section = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.upper()
            continue
        if not stripped or stripped.startswith(";"):
            continue
        if section == "[MAP]" and stripped.lower().startswith("units"):
            parts = stripped.split()
            if len(parts) >= 2:
                map_units = parts[1]
        elif section == "[COORDINATES]":
            parts = stripped.split()
            if len(parts) >= 3:
                coords[parts[0]] = (float(parts[1]), float(parts[2]))

    return {
        "map_units": map_units,
        "is_schematic": map_units.lower() == "none",
        "node_coordinates": coords,
    }


def _validate_and_resolve_metric_crs(
    gdf: gpd.GeoDataFrame,
    target_metric_crs: Optional[str] = None,
) -> Tuple[gpd.GeoDataFrame, str, List[str]]:
    """
    Ensure GeoDataFrame is in a projected CRS with meter units.
    Raises ValueError if CRS is missing.
    """
    warnings: List[str] = []
    if gdf.crs is None:
        raise ValueError(
            "CRS is missing. Provide a valid EPSG/CRS string (e.g. 'EPSG:4326' or a UTM EPSG) "
            "before running spatial distance calculations."
        )

    crs_obj = CRS.from_user_input(gdf.crs)

    if target_metric_crs is not None:
        target_obj = CRS.from_user_input(target_metric_crs)
        if target_obj.is_geographic:
            raise ValueError(
                f"Target CRS '{target_metric_crs}' is geographic (degrees). "
                "Distances must be calculated in a projected metric CRS."
            )
        return gdf.to_crs(target_obj), target_obj.to_string(), warnings

    if crs_obj.is_geographic:
        utm_crs = gdf.estimate_utm_crs()
        warnings.append(
            f"Input CRS '{crs_obj.to_string()}' uses degrees; reprojected to '{utm_crs.to_string()}' "
            "so distances are computed accurately in meters."
        )
        return gdf.to_crs(utm_crs), utm_crs.to_string(), warnings

    axis_units = [axis.unit_name.lower() for axis in crs_obj.axis_info]
    if not any("metre" in u or "meter" in u for u in axis_units):
        raise ValueError(
            f"Projected CRS '{crs_obj.to_string()}' does not use meter units ({axis_units})."
        )

    return gdf, crs_obj.to_string(), warnings


def build_sewer_geodataframe(
    sewer_geojson: Optional[Dict[str, Any]] = None,
    crs: Optional[str] = None,
) -> Tuple[gpd.GeoDataFrame, bool]:
    """
    Build a GeoDataFrame of sewer conduits/nodes.
    If Member 1 provides real-world sewer GeoJSON coordinates matching their
    water network CRS, use those; otherwise inspect bluepulse_sewer.inp and
    flag that .inp coordinates are schematic ('Units None').
    """
    if sewer_geojson is not None:
        features = sewer_geojson.get("features", [])
        if not features:
            raise ValueError("Provided sewer_geojson contains no features.")
        rows = []
        for feat in features:
            if not isinstance(feat, dict) or not feat.get("geometry"):
                raise ValueError("Each GeoJSON feature in sewer_geojson must include a valid 'geometry' object.")
            props = dict(feat.get("properties") or {})
            props["geometry"] = shape(feat["geometry"])
            rows.append(props)
        inferred_crs = crs or sewer_geojson.get("crs", {}).get("properties", {}).get("name")
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=inferred_crs)
        return gdf, False

    parsed = parse_sewer_coordinates_from_inp()
    coords = parsed["node_coordinates"]
    # Build conduit LineStrings from J1->J2 (C1), J2->J3 (C2), J3->O1 (C3)
    edges = [("1", "J1", "J2"), ("2", "J2", "J3"), ("3", "J3", "O1")]
    rows = []
    for swmm_id, u, v in edges:
        if u in coords and v in coords:
            rows.append(
                {
                    "asset_id": CONDUIT_LABEL_MAP[swmm_id],
                    "asset_type": "sewer_conduit",
                    "from_node": u,
                    "to_node": v,
                    "geometry": LineString([coords[u], coords[v]]),
                }
            )
    for nid, pt in coords.items():
        rows.append(
            {
                "asset_id": nid,
                "asset_type": "sewer_node",
                "from_node": nid,
                "to_node": nid,
                "geometry": Point(pt),
            }
        )
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)
    return gdf, parsed["is_schematic"]


def analyze_water_sewer_proximity(
    water_network_geojson: Optional[Dict[str, Any]] = None,
    water_crs: Optional[str] = None,
    sewer_geojson: Optional[Dict[str, Any]] = None,
    sewer_crs: Optional[str] = None,
    target_metric_crs: Optional[str] = None,
    thresholds_m: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Compute distances in meters between sewer assets (Member 3) and
    drinking-water pipelines (Member 1).

    If water_network_geojson is None, does NOT invent drinking-water coordinates;
    instead returns status='awaiting_member1_water_network_data' and documents
    the exact GeoJSON input schema required from Member 1.
    """
    thresh = thresholds_m or dict(DEFAULT_PROXIMITY_THRESHOLDS_M)
    inp_meta = parse_sewer_coordinates_from_inp()

    if water_network_geojson is None:
        return {
            "status": "awaiting_member1_water_network_data",
            "message": (
                "No drinking-water pipeline geometries were provided by Member 1. "
                "BluePulse never fabricates water-network coordinates."
            ),
            "sewer_inp_coordinate_metadata": {
                "map_units": inp_meta["map_units"],
                "is_schematic_unprojected": inp_meta["is_schematic"],
                "nodes_found": list(inp_meta["node_coordinates"].keys()),
                "note": (
                    "bluepulse_sewer.inp currently uses schematic 'Units None' map coordinates. "
                    "To compute real-world proximity, provide georeferenced GeoJSON geometries "
                    "with an explicit CRS (e.g., EPSG:4326 or local UTM EPSG) for both networks."
                ),
            },
            "required_member1_schema": {
                "format": "GeoJSON FeatureCollection",
                "crs": "Explicit CRS string such as 'EPSG:4326' or projected UTM EPSG in meters",
                "required_feature_properties": ["pipe_id", "diameter_m", "material", "pressure_zone"],
                "geometry_types": ["LineString", "MultiLineString"],
            },
            "proximity_pairs": [],
        }

    features = water_network_geojson.get("features", [])
    if not features:
        raise ValueError("Member 1 water_network_geojson contains no features.")

    water_rows = []
    for idx, feat in enumerate(features):
        if not isinstance(feat, dict) or not feat.get("geometry"):
            raise ValueError("Each GeoJSON feature in water_network_geojson must include a valid 'geometry' object.")
        props = dict(feat.get("properties") or {})
        if "pipe_id" not in props:
            props["pipe_id"] = f"W_PIPE_{idx + 1}"
        props["geometry"] = shape(feat["geometry"])
        water_rows.append(props)

    inferred_water_crs = (
        water_crs
        or water_network_geojson.get("crs", {}).get("properties", {}).get("name")
    )
    water_gdf = gpd.GeoDataFrame(water_rows, geometry="geometry", crs=inferred_water_crs)
    water_proj, metric_crs_str, warnings = _validate_and_resolve_metric_crs(
        water_gdf, target_metric_crs=target_metric_crs
    )

    if sewer_geojson is None:
        raise ValueError(
            "Real-world sewer_geojson (with CRS) is required when comparing against georeferenced "
            "Member 1 water pipelines, because bluepulse_sewer.inp only contains schematic 'Units None' coordinates."
        )

    sewer_gdf, _ = build_sewer_geodataframe(sewer_geojson=sewer_geojson, crs=sewer_crs)
    sewer_proj, _, sewer_warnings = _validate_and_resolve_metric_crs(
        sewer_gdf, target_metric_crs=metric_crs_str
    )
    warnings.extend(sewer_warnings)

    proximity_pairs: List[Dict[str, Any]] = []
    for _, s_row in sewer_proj.iterrows():
        s_geom = s_row.geometry
        s_id = str(s_row.get("asset_id", "UNKNOWN_SEWER"))
        s_type = str(s_row.get("asset_type", "sewer_asset"))

        distances = water_proj.geometry.distance(s_geom)
        nearest_idx = distances.idxmin()
        nearest_dist = float(distances.loc[nearest_idx])
        w_row = water_proj.loc[nearest_idx]

        if nearest_dist <= thresh["critical"]:
            tier = "CRITICAL_PROXIMITY"
        elif nearest_dist <= thresh["high"]:
            tier = "HIGH_PROXIMITY"
        elif nearest_dist <= thresh["moderate"]:
            tier = "MODERATE_PROXIMITY"
        else:
            tier = "LOW_PROXIMITY"

        proximity_pairs.append(
            {
                "sewer_asset_id": s_id,
                "sewer_asset_type": s_type,
                "nearest_water_pipe_id": str(w_row["pipe_id"]),
                "distance_m": round(nearest_dist, 3),
                "proximity_tier": tier,
                "water_pipe_material": w_row.get("material"),
                "water_pipe_diameter_m": w_row.get("diameter_m"),
            }
        )

    proximity_pairs.sort(key=lambda item: item["distance_m"])

    return {
        "status": "completed",
        "projected_crs_used": metric_crs_str,
        "distance_units": "meters",
        "thresholds_m": thresh,
        "warnings": warnings,
        "nearby_critical_or_high_count": sum(
            1 for p in proximity_pairs if p["proximity_tier"] in ("CRITICAL_PROXIMITY", "HIGH_PROXIMITY")
        ),
        "proximity_pairs": proximity_pairs,
    }
