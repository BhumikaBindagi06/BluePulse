# Technical Report – BluePulse Member 3 (Sewer & Sanitation Module)

## 1. Hydraulic Model Overview (`bluepulse_sewer.inp`)

The baseline model represents a 300-meter gravity sanitary sewer reach in SI (`CMS`) units solved using EPA SWMM 5.2 Dynamic Wave (`DYNWAVE`) routing over a 6-hour window (`2026-01-01 00:00:00` to `06:00:00`, 10-second routing step, 5-minute report step):

- **Junctions:** `J1` (invert 100 m), `J2` (invert 99 m), `J3` (invert 98 m), each with `MaxDepth = 2.0 m` and no surface ponding (`ALLOW_PONDING = NO`).
- **Outfall:** `O1` (invert 97 m, `FREE` boundary condition).
- **Conduits:** `1` (`C1`: `J1 -> J2`), `2` (`C2`: `J2 -> J3`), `3` (`C3`: `J3 -> O1`), each 100 m long, circular diameter `0.30 m`, Manning's `n = 0.013`, 1% slope (`Q_full ≈ 0.0967 CMS`).
- **Baseline Inflow:** Constant dry-weather inflow of `0.005 CMS` (`5 L/s`) at `J1`.

### Important Note on Original Telemetry Extraction
In the earlier script `simulation/extract_readings.py`, PySWMM's `Link` object did not expose a `.velocity` attribute, so `link.depth` was accidentally saved under the column names `C1_velocity_mps`, `C2_velocity_mps`, and `C3_velocity_mps` in `data/normal_readings.csv`. Those original files are preserved untouched as historical experimental evidence (`J2` mean depth `0.046065 m`, 120% threshold `0.055278 m`, `2,131/2,160` blockage exceedances).  
In the completed `sewer_module/simulation.py`, **true hydraulic velocities** are extracted in two cross-validated ways:
1. Step-by-step mean velocity `Q / (V / L)` from PySWMM `link.flow` and `link.volume` (`0.720 m/s` at steady normal flow).
2. Official SWMM `.out` binary report series via `pyswmm.Output` (`LinkAttribute.FLOW_VELOCITY`, `LinkAttribute.CAPACITY`, `NodeAttribute.FLOODING_LOSSES`, `SystemAttribute.RAINFALL`).

---

## 2. Fault Scenarios & Engineering Assumptions

All fault models are generated separately from `bluepulse_sewer.inp` in `sewer_module/models/scenarios/`:

1. **`partial_blockage`** (`bluepulse_blockage.inp`, preserved): Conduit `C2` diameter reduced from `0.30 m` to `0.15 m` (75% area loss). Causes localized depth increase at `J2` (`0.062 m` peak) without surcharge or flooding; flow stabilizes near `0.005 CMS`.
2. **`severe_blockage`**: Conduit `C2` diameter reduced to `0.06 m` (96% area loss) with `n = 0.025`. Causes backwater surcharge at `J1` (`1.05 m`) and manhole flooding at `J2` (`2.00 m`, `0.00414 CMS` flood loss), starving downstream `C2`/`C3` flow (`0.001 CMS`).
3. **`heavy_rainfall`**: Adds `RG1` (`STORM_TS`, peak `60 mm/hr`) and two 4.5 ha urban catchments (`S1 -> J1`, `S2 -> J2`, 85% impervious). Triggers network-wide surcharge and simulated flooding at `J1`, `J2`, and `J3`.
4. **`sudden_inflow`**: Injects an abnormal shock discharge (`SURGE_TS`, peak `0.14 CMS` between `01:00` and `02:30`) at `J2`, simulating an illegal dump or sudden upstream surge. Causes `J2` flooding and upstream/downstream surcharge (`J1`, `J3`).
5. **`downstream_siltation`**: Conduit `C3` diameter reduced to `0.08 m` with `n = 0.030`, creating downstream backwater flooding at `J3` (`2.00 m`) and surcharge at `J2` (`1.04 m`).

---

## 3. Anomaly Detection Methodology (`sewer_module/anomaly_detection.py`)

Each junction (`J1`, `J2`, `J3`) and conduit (`C1`, `C2`, `C3`) is monitored independently:
- **Threshold Detection:** Flags junction depths exceeding `120%` of the normal baseline mean (`1.20 * baseline_mean`), and post-startup (`>= 15 min`) conduit flow/velocity surges (`> 150%`) or drops (`< 70%`).
- **Z-Score Detection:** Computes `z = (observed - baseline_mean) / max(baseline_std, noise_floor)` where physical noise floors (`2 mm` depth, `0.0005 CMS` flow, `0.05 m/s` velocity) prevent division-by-near-zero false alarms in steady-state segments, and negative Z-scores are suppressed during the initial 15-minute dry-pipe fill-up transient.
- **Validated Isolation Forest (Optional ML):** Trained on post-startup steady-state normal multi-sensor features (`StandardScaler` + `IsolationForest`, `contamination=0.01`). Its outputs are only enabled if normal-baseline validation achieves a false-positive rate `<= 5%`.
- **Interpretable Alerts:** Every alert records `timestamp`, `asset_id`, `metric`, `observed_value`, `baseline_value`, `threshold`, `z_score`, `detection_method`, `severity`, and a `suspected_condition` hypothesis explicitly marked as a hydraulic indicator rather than confirmed fault proof.

---

## 4. Overflow Risk Assessment (`sewer_module/risk_assessment.py`)

Risk is scored transparently on a `0–100` scale at every step:
- **Depth Fill Ratio (`0–40 pts`):** `40 * min(1, depth / max_depth)` (`max_depth = 2.0 m`).
- **Conduit Capacity Utilization (`0–20 pts`):** `20 * min(1, |flow| / Q_full)`.
- **Abnormal Condition Duration (`0–15 pts`):** `15 * min(1, continuous_abnormal_minutes / 60)`.
- **Active Rainfall (`0–10 pts`):** `10 * min(1, rainfall_mm_hr / 50)`.
- **Surcharge / Flooding State (`0–15 pts`):** `+7.5 pts` when depth exceeds pipe crown (`SURCHARGED`); `+15 pts` when SWMM reports node flooding (`FLOODING_SIMULATED`).

Hydraulic states are strictly separated:
1. `NORMAL` — within baseline limits.
2. `ANOMALY_ONLY` — exceeds statistical/threshold limits, below pipe crown.
3. `SURCHARGED` — water rises above pipe crown (`> 0.30 m` or blocked diameter), still below manhole rim (`< 2.0 m`).
4. `FLOODING_SIMULATED` — water reaches manhole rim (`2.0 m`) with SWMM `flooding > 0 CMS`.
5. `CONFIRMED_OVERFLOW` — assigned **only** when simulated flooding is corroborated by physical field/sensor confirmation.

---

## 5. Spatial & Cross-Contamination Logic

- **Spatial (`spatial_analysis.py`):** Uses GeoPandas/Shapely and enforces CRS validation. Any geographic CRS (degrees, e.g. `EPSG:4326`) is automatically reprojected to a metric UTM CRS before computing Euclidean distances in meters. Missing Member 1 water-network geometry returns `status = "awaiting_member1_water_network_data"` without fabricating pipes.
- **Cross-Contamination (`cross_contamination.py`):** Combines Member 3 sewer hazard (`0–35 pts`), Member 1 spatial proximity (`0–25 pts`) and water pressure (`0–20 pts`), and Member 2 chlorine residual / turbidity (`0–20 pts`). Missing team inputs increase `uncertainty_level` (`LOW`, `MODERATE`, `HIGH`), and results are always labeled as **potential risk / investigation priority**, never confirmed contamination.

---

## 6. Limitations & Future Improvements

1. **Schematic Coordinates in `.inp`:** `bluepulse_sewer.inp` uses arbitrary `[MAP] Units None` coordinates (`7848..7853, 10524`), so real-world GIS mapping requires georeferenced coordinates from Member 1 / campus/city GIS.
2. **Steady Dry-Weather Baseline:** The current normal model uses constant `0.005 CMS` inflow instead of a diurnal 24-hour domestic wastewater pattern; adding a diurnal `[PATTERNS]` curve would improve realism for longer simulations.
3. **Single-Branch Topology:** The 3-conduit linear network demonstrates upstream/downstream propagation cleanly, and can be expanded to branched sub-networks once full campus/city layout data is available.
4. **No Water Quality Constituents in SWMM:** Currently SWMM tracks hydraulic quantity only; pollutant routing (`[POLLUTANTS]`) can be added if BOD/TSS/pathogen concentration estimates are later needed.
