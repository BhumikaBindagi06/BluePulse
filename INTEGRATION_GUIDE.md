# BluePulse – Member 3 Integration Guide

**Module:** BluePulse Member 3 – Sewer & Sanitation  
**Entrypoint:** `main.py` (`app`) and `sewer_module.api.router`  
**Related Contracts:** See [INTEGRATION_CONTRACTS.md](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/INTEGRATION_CONTRACTS.md)

---

## 1. Architecture & Standalone Readiness

Member 3 (`sewer_module/`) runs **independently** even when Member 1 (drinking-water GIS & pressures) and Member 2 (water-quality sensors) data are unavailable:
* Hydraulic simulation (`normal`, `partial_blockage`, `severe_blockage`, `heavy_rainfall`, `sudden_inflow`, `downstream_siltation`), anomaly detection, overflow risk assessment, and `/api/v1/sewer/*` endpoints operate on validated local outputs under `data/outputs/`.
* When Member 1 or Member 2 inputs are absent:
  * `POST /api/v1/sewer/spatial/proximity` returns HTTP `200` with `status: "awaiting_member1_water_network_data"` and `proximity_pairs: []` without fabricating pipe coordinates.
  * `POST /api/v1/sewer/cross-contamination/assess` keeps missing fields as `null`, lists them explicitly in `missing_inputs`, lowers `input_completeness_pct` (`20.0%` with 0 external inputs), sets `uncertainty_level: "HIGH"`, and sets `status_label: "INSUFFICIENT_DATA_AWAITING_TEAM_INPUTS"` (`investigation_priority: "INDETERMINATE_AWAITING_TEAM_INPUTS"`). Missing values are **never** coerced to `0.0`.
* **Note on Heavy Rainfall Corrected Model:** The separate `WARNING 09`-corrected model ([bluepulse_heavy_rainfall_corrected.inp](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/sewer_module/models/scenarios/bluepulse_heavy_rainfall_corrected.inp)) and its `heavy_rainfall_corrected_*` CSV outputs are stored alongside the preserved original `heavy_rainfall` artifacts without altering the 6-scenario registry returned by `GET /api/v1/sewer/scenarios`.

---

## 2. How Member 4 Connects the Sewer Module

### Option A: Mount Directly Inside Member 4's FastAPI Backend (Recommended)

Add the Member 3 project package (`sewer_module/`) to Member 4's Python environment (or `PYTHONPATH`) and mount `sewer_router` into Member 4's FastAPI application:

```python
from fastapi import FastAPI
from sewer_module.api import router as sewer_router

app = FastAPI(title="BluePulse Digital Twin Backend")
app.include_router(sewer_router)
```

> [!IMPORTANT]
> `sewer_module/config.py` resolves `PROJECT_DIR` relative to `sewer_module/config.py` (`Path(__file__).resolve().parent.parent`), so `data/outputs/` and `sewer_module/models/` must stay in place relative to `sewer_module/` (or be packaged together).

### Option B: Run Member 3 as a Standalone Microservice

Launch from the `BluePulse` repository root using the configured virtual environment:

```powershell
.\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8003 --reload
```

Interactive OpenAPI documentation is served at `http://127.0.0.1:8003/docs` and `http://127.0.0.1:8003/openapi.json`.

### Option C: Consume Pre-Exported Static JSON Artifacts

For batch ingestion or frontend prototyping without live simulation calls, Member 4 can read the JSON files under `data/outputs/api_exports/`:
* `fault_events.json`
* `master_integration_summary.json`
* `spatial_proximity_status.json`
* `cross_contamination_indicators.json`
* `integration_contracts.json`

---

## 3. Complete API Endpoint Reference

| Method & Path | Query / Body Parameters | Success (`200`) Response | Error Codes & Causes |
| :--- | :--- | :--- | :--- |
| `GET /` | None | `{service, docs_url, sewer_health_url}` | — |
| `GET /api/v1/sewer/health` | None | `{module, status, configured_scenarios, simulated_scenarios_ready}` | — |
| `GET /api/v1/sewer/scenarios` | None | JSON array of 6 `ScenarioInfo` objects | — |
| `GET /api/v1/sewer/readings/{scenario}` | Path: `scenario`<br>Query: `limit` (`1..2500`, default `100`), `offset` (`>=0`, default `0`), `resolution` (`"step"` \| `"report"`, default `"step"`) | `{scenario, resolution, total_records, offset, returned_records, records}` | `404` unknown scenario or missing CSV;<br>`422` invalid query parameter bounds/pattern |
| `GET /api/v1/sewer/anomalies/{scenario}` | Path: `scenario`<br>Query: `asset_id` (optional), `severity` (optional), `limit` (`1..5000`, default `200`) | `{scenario, total_matching_alerts, returned_alerts, alerts}` | `404` unknown scenario or missing alerts CSV;<br>`422` invalid `limit` |
| `GET /api/v1/sewer/risk/{scenario}` | Path: `scenario` | `{network_max_risk_score, network_highest_status, asset_summaries, risk_csv}` (or CSV fallback summary) | `404` unknown scenario or missing risk CSV |
| `POST /api/v1/sewer/spatial/proximity` | JSON `SpatialProximityRequest` (`water_network_geojson`, `water_crs`, `sewer_geojson`, `sewer_crs`, `target_metric_crs`) | If `water_network_geojson` is `null`: `status="awaiting_member1_water_network_data"`, `proximity_pairs=[]`.<br>If valid GeoJSON + CRS supplied: `status="completed"`, `projected_crs_used`, `distance_units="meters"`, `proximity_pairs` | `422` missing CRS, empty features, missing `geometry`, missing `sewer_geojson` when water GeoJSON is given, geographic `target_metric_crs`, or non-meter projected CRS |
| `POST /api/v1/sewer/cross-contamination/assess` | JSON `CrossContaminationRequest` (required: `sewer_asset_id`, `timestamp`, `sewer_hydraulic_state`, `sewer_risk_score` `0..100`; optional: Member 1/2 fields) | Risk score (`0..100`), `investigation_priority`, `uncertainty_level`, `input_completeness_pct`, `score_breakdown`, `available_inputs`, `missing_inputs`, `contributing_factors`, `disclaimer` | `422` Pydantic validation error (e.g. missing required field, `sewer_risk_score` outside `0..100`, negative `distance_to_water_pipe_m`/`chlorine_residual_mg_l`/`turbidity_ntu`) |
| `GET /api/v1/sewer/schemas/integration` | None | `integration_contracts.json` contents | — |

---

## 4. Coordinate Reference System (CRS) Requirements for Spatial Analysis

`sewer_module/spatial_analysis.py` enforces strict CRS validation before computing any distances:
1. **Explicit CRS Required:** Both `water_network_geojson` and `sewer_geojson` must supply a valid CRS (via `water_crs` / `sewer_crs` request fields or GeoJSON `crs.properties.name`). Missing CRS raises HTTP `422`.
2. **No Euclidean Distances in Degrees:** Geographic CRSs (e.g., `EPSG:4326`) are **never** used directly for `.distance()`. When a geographic CRS is detected, `spatial_analysis.py` automatically estimates and reprojects both layers to the local UTM projected CRS in meters (e.g., `EPSG:32643`) and appends a warning note to `warnings`.
3. **Metric Units Verification:** If `target_metric_crs` is supplied, it must be a projected CRS with meter units (`metre`/`meter`); geographic or non-meter CRSs are rejected with HTTP `422`.
4. **Why `sewer_geojson` Is Required Alongside Member 1 Data:** `sewer_module/models/bluepulse_sewer.inp` uses schematic `[MAP] Units None` local coordinates (`7848.6–7853.2`). Those schematic coordinates cannot be overlaid onto real-world Member 1 pipelines; Member 1 / GIS onboarding must supply georeferenced `sewer_geojson` in a real-world CRS.

---

## 5. Synthetic Integration Test Fixtures

Pre-built synthetic fixtures for full end-to-end integration testing are located at:
* [synthetic_integration_fixtures.json](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/tests/fixtures/synthetic_integration_fixtures.json)

All records and IDs in that file carry `"_synthetic_test_data": true` and `SYNTHETIC_TEST_*` prefixes to prevent confusion with real field data. The automated integration suite in [test_sewer_module.py](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/tests/test_sewer_module.py) exercises both standalone degraded mode and the full synthetic workflow (`risk` -> `spatial/proximity` -> `cross-contamination/assess`).

---

## 6. Member 4 Handover Checklist

- [ ] **Environment & Dependencies:** Install/verify Python packages from [requirements.txt](file:///c:/Users/ABHIJNA%20A/OneDrive/Documents/BluePulse/requirements.txt) (`fastapi`, `pyswmm`, `swmm-toolkit`, `pandas`, `scikit-learn`, `geopandas`, `pyproj`, `shapely`, `pydantic`).
- [ ] **Router Mounting:** Import and mount `from sewer_module.api import router as sewer_router` in Member 4's FastAPI app (or proxy to port `8003`).
- [ ] **Health & Smoke Verification:** Call `GET /api/v1/sewer/health` and confirm `"status": "healthy"` and all `6` scenarios appear in `simulated_scenarios_ready`.
- [ ] **Scenario Telemetry & Risk Wiring:** Wire dashboard views to `GET /api/v1/sewer/scenarios`, `/readings/{scenario}`, `/anomalies/{scenario}`, and `/risk/{scenario}`.
- [ ] **Graceful Missing-Data Handling in UI:** Ensure dashboard displays `uncertainty_level`, `input_completeness_pct`, `missing_inputs`, and `disclaimer` verbatim—do **not** substitute `0` when Member 1 or Member 2 fields are `null`.
- [ ] **Member 1 Onboarding:** When Member 1 delivers real `water_network_geojson` + `sewer_geojson` + CRS + `water_pressure_bar`, validate via `POST /api/v1/sewer/spatial/proximity` (confirm `distance_units: "meters"` and expected `projected_crs_used`).
- [ ] **Member 2 Onboarding:** Connect `chlorine_residual_mg_l` and `turbidity_ntu` streams into `POST /api/v1/sewer/cross-contamination/assess`.
- [ ] **Synthetic End-to-End Dry Run:** Execute `.\.venv\Scripts\python.exe -m pytest -v` (confirm all tests pass) and test the frontend against `tests/fixtures/synthetic_integration_fixtures.json` before switching to live Member 1/2 feeds.
