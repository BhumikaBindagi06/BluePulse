# BluePulse – Sewer & Sanitation Module (Member 3)

**Project:** BluePulse – Multi-Agent Digital Twin for Smart Water Networks  
**Module Owner:** Member 3 – Sewer & Sanitation Network Simulation, Monitoring, Risk Assessment & Integration  
**Tools:** EPA SWMM 5.2 (`swmm-toolkit`), PySWMM 2.2.0, Python 3.13, Pandas, NumPy, Matplotlib, Scikit-Learn, GeoPandas/Shapely, FastAPI

---

## 1. Folder Structure

```text
BluePulse/
├── main.py                                 # FastAPI app + full pipeline CLI runner
├── pytest.ini                              # Pytest configuration
├── requirements.txt                        # Python dependencies
├── README.md                               # Setup, usage, and Member 4 integration guide
├── docs/
│   └── TECHNICAL_REPORT.md                 # Hydraulic assumptions, detection, risk, limitations
├── sewer_module/                           # Completed Member 3 modular package
│   ├── __init__.py
│   ├── config.py                           # Paths, network geometry, scenario specs, thresholds
│   ├── inp_builder.py                      # Generates separate fault .inp models safely
│   ├── simulation.py                       # PySWMM step runner + .out & .rpt extractor
│   ├── anomaly_detection.py                # Threshold, Z-score, & validated Isolation Forest
│   ├── risk_assessment.py                  # Explainable overflow risk & state classification
│   ├── spatial_analysis.py                 # CRS-validated GeoPandas/Shapely proximity engine
│   ├── cross_contamination.py              # Multi-member potential risk indicator
│   ├── visualization.py                    # Non-interactive Matplotlib comparison charts
│   ├── schemas.py                          # Pydantic contracts for Member 4 / Member 1 / Member 2
│   ├── api.py                              # FastAPI APIRouter (/api/v1/sewer/...)
│   ├── pipeline.py                         # End-to-end orchestration & JSON/CSV export
│   └── models/
│       ├── bluepulse_sewer.inp             # Preserved original normal model
│       ├── bluepulse_blockage.inp          # Preserved original 0.15 m blockage model
│       └── scenarios/                      # Generated fault models & metadata
├── simulation/                             # Original working scripts (preserved)
├── monitoring/                             # Original analysis scripts (preserved)
├── data/
│   ├── normal_readings.csv                 # Preserved original 2,160-row baseline dataset
│   ├── blockage_readings.csv               # Preserved original 2,160-row blockage dataset
│   ├── detected_anomalies.csv              # Preserved original J2 threshold output
│   ├── multi_node_anomalies.csv            # Preserved original multi-node output
│   ├── *.png                               # Preserved original plots
│   └── outputs/                            # New structured module outputs
│       ├── simulations/                    # Step (10 s) & SWMM .out report (5 min) CSVs
│       ├── anomalies/                      # Per-scenario alerts & annotated readings
│       ├── risk/                           # Per-scenario overflow risk timelines
│       ├── plots/                          # Multi-scenario comparison graphs
│       └── api_exports/                    # Standardized JSON files for Member 4
└── tests/
    └── test_sewer_module.py                # Automated pytest verification suite
```

---

## 2. Quick Setup (Windows)

Activate the existing virtual environment (or create one and install `requirements.txt`):

```powershell
# Using existing .venv
.\.venv\Scripts\Activate.ps1

# Or install dependencies into a fresh venv
pip install -r requirements.txt
```

---

## 3. How to Run

### A. Run the Complete Simulation, Monitoring, Risk & Export Pipeline
```powershell
.\.venv\Scripts\python.exe main.py
```
This preserves all original files in `data/` and `sewer_module/models/`, runs all 6 SWMM scenarios (`normal`, `partial_blockage`, `severe_blockage`, `heavy_rainfall`, `sudden_inflow`, `downstream_siltation`), and writes outputs under `data/outputs/`.

### B. Run Automated Tests
```powershell
.\.venv\Scripts\pytest.exe -v
```

### C. Launch the FastAPI Service (for Member 4 Integration Testing)
```powershell
.\.venv\Scripts\uvicorn.exe main:app --reload --port 8003
```
Interactive API documentation is then available at `http://127.0.0.1:8003/docs`.

---

## 4. Integration Guide for Member 4 (FastAPI Backend)

Member 4 can mount the Member 3 router directly into the team's main FastAPI app without modifying internal simulation code:

```python
from fastapi import FastAPI
from sewer_module.api import router as sewer_router

app = FastAPI(title="BluePulse Digital Twin Backend")
app.include_router(sewer_router)
```

### Available Endpoints
- `GET /api/v1/sewer/health` — Module status and ready scenarios.
- `GET /api/v1/sewer/scenarios` — Scenario definitions, SWMM modifications, and assumptions.
- `GET /api/v1/sewer/readings/{scenario}` — Simulated telemetry (`step` 10-second or `report` 5-minute resolution).
- `GET /api/v1/sewer/anomalies/{scenario}` — Interpretable alerts with asset, baseline, threshold, Z-score, and suspected cause.
- `GET /api/v1/sewer/risk/{scenario}` — Junction overflow risk summary (`NORMAL`, `ANOMALY_ONLY`, `SURCHARGED`, `FLOODING_SIMULATED`, `CONFIRMED_OVERFLOW`).
- `POST /api/v1/sewer/spatial/proximity` — Accepts Member 1's drinking-water GeoJSON + CRS and computes projected meter distances.
- `POST /api/v1/sewer/cross-contamination/assess` — Combines Member 3 sewer state with Member 1 (proximity, pressure) and Member 2 (chlorine, turbidity) inputs.
- `GET /api/v1/sewer/schemas/integration` — Machine-readable input/output contracts.

### Inputs Still Required From Other Team Members
1. **Member 1 (Drinking-Water Network):**
   - Georeferenced GeoJSON `FeatureCollection` of drinking-water pipelines (`pipe_id`, `diameter_m`, `material`, `pressure_zone`) with an explicit CRS (e.g., `EPSG:4326` or UTM).
   - Georeferenced real-world coordinates for the sewer network (since `bluepulse_sewer.inp` currently uses schematic `Units None` map coordinates).
   - Live/simulated drinking-water line pressure (`water_pressure_bar`).
2. **Member 2 (Water Quality Sensors):**
   - Free chlorine residual (`chlorine_residual_mg_l`) and turbidity (`turbidity_ntu`) readings linked by zone/timestamp.
