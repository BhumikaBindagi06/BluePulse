# BluePulse – Member 3 Integration Contracts

**Module:** BluePulse Member 3 – Sewer & Sanitation  
**Router Prefix:** `/api/v1/sewer`  
**Machine-Readable Contract Endpoint:** `GET /api/v1/sewer/schemas/integration`  
**Static Export:** `data/outputs/api_exports/integration_contracts.json`

> [!NOTE]
> All example payloads involving Member 1 or Member 2 data in this document use **synthetic test values** (prefixed with `SYNTHETIC_TEST_`) solely to illustrate the schemas. Missing Member 1 or Member 2 inputs must be omitted or passed as `null`—never replaced with `0` or fabricated measurements.

---

## 1. Inputs Expected from Member 1 (Drinking-Water Network & Pressure)

Member 1 provides only the drinking-water pipeline geometry, its coordinate reference system metadata, and drinking-water line pressure. Sewer geometry is owned by Member 3 (Section 2).

### 1.1 Spatial Proximity Request (`POST /api/v1/sewer/spatial/proximity`)

| Field | Type | Required | Units / Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| `water_network_geojson` | `object \| null` | Optional (nullable) | GeoJSON `FeatureCollection` | Drinking-water pipes (`LineString` / `MultiLineString`) with properties `pipe_id` (`string`), `diameter_m` (`number`, m), `material` (`string`), `pressure_zone` (`string`). When `null`, endpoint returns `awaiting_member1_water_network_data`. |
| `water_crs` | `string \| null` | Required if `water_network_geojson` provided (unless embedded in GeoJSON `crs`) | EPSG / CRS string | Explicit CRS such as `"EPSG:4326"` or projected UTM EPSG in meters (e.g. `"EPSG:32643"`). |
| `target_metric_crs` | `string \| null` | Optional | Projected metric EPSG | Optional projected CRS in meters; if `null`, UTM zone is auto-estimated for geographic CRSs. Geographic CRSs (e.g. `"EPSG:4326"`) are rejected as `target_metric_crs` (`422`). |

### 1.2 Drinking-Water Pressure & Derived Proximity (`POST /api/v1/sewer/cross-contamination/assess`)

| Field | Type | Required | Units | Description |
| :--- | :--- | :--- | :--- | :--- |
| `nearest_water_pipe_id` | `string \| null` | Optional | Identifier | ID of nearest drinking-water pipe from Member 1 / spatial proximity output. |
| `distance_to_water_pipe_m` | `float \| null` | Optional (`>= 0.0`) | meters (`m`) | Metric distance between sewer asset and water pipe. Thresholds: critical `<= 5.0 m`, high `<= 15.0 m`, moderate `<= 30.0 m`. Pass `null` when unavailable. |
| `water_pressure_bar` | `float \| null` | Optional | `bar` | Drinking-water pipe/zone pressure (`< 1.0 bar` low-pressure intrusion risk; `<= 0.2 bar` critical/negative pressure). Pass `null` when unavailable (never pass `0.0` for missing data, as `0.0 bar` is evaluated as critical zero pressure). |

---

## 2. Inputs Expected from Member 3 (Sewer & Sanitation Geometry)

Member 3 owns and is responsible for providing the sewer network geometry. Member 1 is responsible only for the drinking-water network geometry.

### 2.1 Sewer Geometry for Spatial Proximity (`POST /api/v1/sewer/spatial/proximity`)

| Field | Type | Required | Units / Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| `sewer_geojson` | `object \| null` | Optional (nullable; pending georeferenced data) | GeoJSON `FeatureCollection` | Georeferenced sewer pipes/nodes (`Point` / `LineString`) with properties `asset_id` (`string`) and `asset_type` (`string`). Member 3 will provide this when real-world georeferenced sewer geometry is available. |
| `sewer_crs` | `string \| null` | Required if `sewer_geojson` is provided (unless embedded in GeoJSON `crs`) | EPSG / CRS string | Explicit CRS matching the real-world sewer coordinates. |

**Current geometry limitation:** The current EPA SWMM sewer model uses schematic/local coordinates (`[MAP] Units None`), not real-world georeferenced coordinates. These schematic coordinates must not be treated as GIS locations or used to calculate real-world proximity to drinking-water pipes. Member 3 will provide georeferenced sewer GeoJSON with an explicit CRS when available. Until then, `sewer_geojson` and `sewer_crs` must remain `null`/unavailable for real-world spatial proximity calculations.

---

## 3. Inputs Expected from Member 2 (Water Quality Sensors)

Member 2 provides drinking-water quality sensor telemetry used in `POST /api/v1/sewer/cross-contamination/assess`.

| Field | Type | Required | Units | Description |
| :--- | :--- | :--- | :--- | :--- |
| `chlorine_residual_mg_l` | `float \| null` | Optional (`>= 0.0`) | `mg/L` | Free chlorine residual (`< 0.2 mg/L` triggers WHO low-residual alert, `+12 pts`). Pass `null` when unavailable. |
| `turbidity_ntu` | `float \| null` | Optional (`>= 0.0`) | `NTU` | Water turbidity (`> 1.0 NTU` moderate `+4 pts`; `> 5.0 NTU` elevated `+8 pts`). Pass `null` when unavailable. |

### Example Combined Input JSON (`POST /api/v1/sewer/cross-contamination/assess`)

**A. Standalone Mode (Member 1 & Member 2 Unavailable):**
```json
{
  "sewer_asset_id": "J2",
  "timestamp": "2026-01-01T04:24:01",
  "sewer_hydraulic_state": "FLOODING_SIMULATED",
  "sewer_risk_score": 90.0
}
```

**B. Full Multi-Member Integration Mode (Using Synthetic Test Values):**
```json
{
  "sewer_asset_id": "J2",
  "timestamp": "2026-01-01T04:24:01",
  "sewer_hydraulic_state": "FLOODING_SIMULATED",
  "sewer_risk_score": 90.0,
  "nearest_water_pipe_id": "SYNTHETIC_TEST_W_MAIN_1",
  "distance_to_water_pipe_m": 3.33,
  "water_pressure_bar": 0.1,
  "chlorine_residual_mg_l": 0.08,
  "turbidity_ntu": 6.4
}
```

---

## 4. Outputs Exposed to Member 4 (Backend & Digital Twin Dashboard)

### 4.1 Module Health (`GET /api/v1/sewer/health`)
```json
{
  "module": "BluePulse Member 3 - Sewer & Sanitation",
  "status": "healthy",
  "configured_scenarios": [
    "normal",
    "partial_blockage",
    "severe_blockage",
    "heavy_rainfall",
    "sudden_inflow",
    "downstream_siltation"
  ],
  "simulated_scenarios_ready": [
    "normal",
    "partial_blockage",
    "severe_blockage",
    "heavy_rainfall",
    "sudden_inflow",
    "downstream_siltation"
  ]
}
```

### 4.2 Scenario Metadata (`GET /api/v1/sewer/scenarios` -> `ScenarioInfo[]`)

| Field | Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `name` | `string` | — | Scenario identifier (`normal`, `partial_blockage`, etc.). |
| `title` | `string` | — | Human-readable scenario title. |
| `description` | `string` | — | Hydraulic fault summary. |
| `is_baseline` | `boolean` | — | `true` only for `normal`. |
| `modifications` | `string[]` | — | Parameter changes relative to baseline. |
| `assumptions` | `string[]` | — | Documented modeling assumptions. |
| `conduit_diameters_m` | `object` (`Dict[str, float]`) | meters (`m`) | Circular diameter per SWMM link ID (`"1"`, `"2"`, `"3"`). |

### 4.3 Telemetry Readings (`GET /api/v1/sewer/readings/{scenario}`)

Returns pagination wrapper `{scenario, resolution, total_records, offset, returned_records, records}`:
* **`resolution="step"`** (`38` fields per record, ~10-second SWMM routing steps):
  * Metadata: `timestamp` (`string`), `scenario` (`string`)
  * Junctions `J1`, `J2`, `J3`: `*_depth_m` (`float`, m), `*_head_m` (`float`, m), `*_total_inflow_cms` (`float`, m³/s), `*_flooding_cms` (`float`, m³/s), `*_depth_ratio` (`float`, dimensionless)
  * Outfall `O1`: `O1_depth_m` (`float`, m), `O1_head_m` (`float`, m), `O1_total_inflow_cms` (`float`, m³/s)
  * Conduits `C1`, `C2`, `C3`: `*_flow_cms` (`float`, m³/s), `*_depth_m` (`float`, m), `*_velocity_mps` (`float`, m/s), `*_froude` (`float`, dimensionless), `*_depth_ratio` (`float`, dimensionless), `*_flow_capacity_ratio` (`float`, dimensionless `|Q|/Q_full`)
* **`resolution="report"`** (`34` fields per record, 5-minute SWMM binary `.out` series):
  * `timestamp` (`string`), `scenario` (`string`), `system_rainfall_mm_hr` (`float`, mm/hr), `system_runoff_cms` (`float`, m³/s), `system_flood_losses_cms` (`float`, m³/s), `system_outfall_cms` (`float`, m³/s), per-node `*_depth_m`, `*_head_m`, `*_inflow_cms`, `*_flooding_cms`, and per-conduit `*_flow_cms`, `*_depth_m`, `*_velocity_mps`, `*_capacity_ratio`.

### 4.4 Anomaly Alerts (`GET /api/v1/sewer/anomalies/{scenario}`)

Returns `{scenario, total_matching_alerts, returned_alerts, alerts}` where each item matches `AnomalyAlertRecord`:

| Field | Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `string` | ISO-8601 | Alert timestamp. |
| `scenario` | `string` | — | Scenario name. |
| `asset_id` | `string` | — | `"J1"`, `"J2"`, `"J3"`, `"C1"`, `"C2"`, or `"C3"`. |
| `asset_type` | `string` | — | `"junction"` or `"conduit"`. |
| `metric` | `string` | — | `"depth_m"`, `"flow_cms"`, or `"velocity_mps"`. |
| `observed_value` | `float` | metric unit | Observed value at step. |
| `baseline_value` | `float` | metric unit | Normal baseline mean. |
| `threshold` | `float` | metric unit | Triggered threshold value. |
| `z_score` | `float` | std devs | Standardized deviation with noise-floor protection. |
| `detection_method` | `string` | — | Combined triggers (`threshold_120pct`, `upper_threshold_150pct`, `lower_threshold_70pct`, `z_score`). |
| `severity` | `string` | — | `LOW`, `MODERATE`, `HIGH`, or `CRITICAL`. |
| `suspected_condition` | `string` | — | Hypothesis text (never physical proof). |
| `disclaimer` | `string` | — | Mandatory non-confirmation disclaimer. |

### 4.5 Overflow Risk Summary (`GET /api/v1/sewer/risk/{scenario}`)

Returns `{network_max_risk_score, network_highest_status, asset_summaries, risk_csv}` where each `asset_summaries` item has:

| Field | Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `asset_id` | `string` | — | `"J1"`, `"J2"`, or `"J3"`. |
| `scenario` | `string` | — | Scenario name. |
| `baseline_depth_m` | `float` | m | Mean depth in `normal` baseline. |
| `max_depth_m_observed` | `float` | m | Peak simulated depth. |
| `manhole_rim_depth_m` | `float` | m | Maximum junction depth (`2.0 m`). |
| `max_depth_fill_pct` | `float` | `%` | `max_depth_m_observed / manhole_rim_depth_m * 100`. |
| `connected_downstream_conduit` | `string` | — | Downstream conduit label (`C1`, `C2`, `C3`). |
| `crown_height_m` | `float` | m | Highest connected conduit crown at node. |
| `surcharged_minutes` | `float` | min | Total minutes with `depth > crown_height_m`. |
| `flooded_minutes` | `float` | min | Total minutes with active surface flooding. |
| `max_flooding_cms` | `float` | m³/s | Peak node flooding rate. |
| `max_risk_score` / `mean_risk_score` | `float` | `0–100` | Explainable composite risk score. |
| `highest_hydraulic_state` | `string` | — | `NORMAL`, `ANOMALY_ONLY`, `SURCHARGED`, `FLOODING_SIMULATED`, or `CONFIRMED_OVERFLOW`. |

### 4.6 Spatial Proximity Output (`POST /api/v1/sewer/spatial/proximity`)

**When Member 1 data is unavailable (`water_network_geojson: null`):**
```json
{
  "status": "awaiting_member1_water_network_data",
  "message": "No drinking-water pipeline geometries were provided by Member 1. BluePulse never fabricates water-network coordinates.",
  "sewer_inp_coordinate_metadata": {
    "map_units": "None",
    "is_schematic_unprojected": true,
    "nodes_found": ["J1", "J2", "J3", "O1"],
    "note": "bluepulse_sewer.inp currently uses schematic 'Units None' map coordinates. To compute real-world proximity, Member 1 must provide georeferenced drinking-water GeoJSON and Member 3 must provide georeferenced sewer GeoJSON, each with an explicit CRS (e.g., EPSG:4326 or local UTM EPSG). The current SWMM schematic coordinates are not valid real-world GIS geometry."
  },
  "required_member1_schema": {
    "format": "GeoJSON FeatureCollection",
    "crs": "Explicit CRS string such as 'EPSG:4326' or projected UTM EPSG in meters",
    "required_feature_properties": ["pipe_id", "diameter_m", "material", "pressure_zone"],
    "geometry_types": ["LineString", "MultiLineString"]
  },
  "proximity_pairs": []
}
```

**When valid georeferenced GeoJSONs + CRSs are supplied (Synthetic Example Output):**
```json
{
  "status": "completed",
  "projected_crs_used": "EPSG:32643",
  "distance_units": "meters",
  "thresholds_m": {"critical": 5.0, "high": 15.0, "moderate": 30.0},
  "warnings": [
    "Input CRS 'EPSG:4326' uses degrees; reprojected to 'EPSG:32643' so distances are computed accurately in meters."
  ],
  "nearby_critical_or_high_count": 3,
  "proximity_pairs": [
    {
      "sewer_asset_id": "SYNTHETIC_TEST_J2",
      "sewer_asset_type": "sewer_node",
      "nearest_water_pipe_id": "SYNTHETIC_TEST_W_MAIN_1",
      "distance_m": 3.318,
      "proximity_tier": "CRITICAL_PROXIMITY",
      "water_pipe_material": "DI",
      "water_pipe_diameter_m": 0.25
    }
  ]
}
```

### 4.7 Cross-Contamination Indicator Output (`POST /api/v1/sewer/cross-contamination/assess`)

| Field | Type | Units / Values | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `string` | ISO-8601 | Event timestamp. |
| `sewer_asset_id` | `string` | — | Evaluated sewer asset. |
| `nearest_water_pipe_id` | `string \| null` | — | Paired water pipe ID, or `null` if unavailable. |
| `status_label` | `string` | — | `"INSUFFICIENT_DATA_AWAITING_TEAM_INPUTS"` (0 external inputs) or `"POTENTIAL_RISK_INVESTIGATION_ONLY"` (never confirms contamination). |
| `potential_risk_score` | `float` | `0–100` | Sum of available component scores (`sewer_hazard <= 35`, `spatial_proximity <= 25`, `water_pressure <= 20`, `water_quality <= 20`). |
| `investigation_priority` | `string` | — | `INDETERMINATE_AWAITING_TEAM_INPUTS`, `LOW_INVESTIGATION_PRIORITY`, `MODERATE_INVESTIGATION_PRIORITY`, `HIGH_INVESTIGATION_PRIORITY`, or `CRITICAL_INVESTIGATION_PRIORITY`. |
| `uncertainty_level` | `string` | — | `HIGH` (0 external inputs), `MODERATE` (1–2), `LOW` (3–4). |
| `input_completeness_pct` | `float` | `%` | `(1 + external_present) / 5.0 * 100`. |
| `score_breakdown` | `object` | pts | `{sewer_hazard_pts, spatial_proximity_pts, water_pressure_pts, water_quality_pts}`. |
| `available_inputs` | `string[]` | — | Inputs actually supplied. |
| `missing_inputs` | `string[]` | — | Explicit list of absent Member 1 / Member 2 inputs. |
| `contributing_factors` | `string[]` | — | Human-readable rule explanations. |
| `disclaimer` | `string` | — | Mandatory disclaimer stating field/lab confirmation is required. |

### 4.8 Static JSON Exports (`data/outputs/api_exports/`)
* [fault_events.json](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/data/outputs/api_exports/fault_events.json) — Summary of the 5 non-baseline scenarios for dashboard alerts.
* [spatial_proximity_status.json](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/data/outputs/api_exports/spatial_proximity_status.json) — Current spatial readiness (`awaiting_member1_water_network_data`).
* [cross_contamination_indicators.json](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/data/outputs/api_exports/cross_contamination_indicators.json) — Peak fault-event indicators explicitly reporting `HIGH` uncertainty and `missing_inputs`.
* [integration_contracts.json](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/data/outputs/api_exports/integration_contracts.json) — Machine-readable endpoint and team dependency summary.
* [master_integration_summary.json](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/data/outputs/api_exports/master_integration_summary.json) — Consolidated scenario metadata, RPT diagnostics, anomaly stats, and risk summaries.
