"""
BluePulse Sewer & Sanitation Module (Member 3) Entrypoint.

Usage:
  - Run full simulation, detection, risk, visualization, and export pipeline:
      python main.py
  - Launch FastAPI service for Member 4 integration testing:
      uvicorn main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from sewer_module.api import router as sewer_router
from sewer_module.pipeline import run_full_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="BluePulse Sewer & Sanitation Module API (Member 3)",
    version="1.0.0",
    description=(
        "Hydraulic simulation, anomaly detection, overflow risk assessment, "
        "spatial proximity analysis, and cross-contamination risk indication "
        "for the BluePulse Smart Water Network Digital Twin."
    ),
)
app.include_router(sewer_router)


@app.get("/")
def root() -> dict:
    return {
        "service": "BluePulse Member 3 - Sewer & Sanitation",
        "docs_url": "/docs",
        "sewer_health_url": "/api/v1/sewer/health",
    }


if __name__ == "__main__":
    summary = run_full_pipeline()
    print("\n=== BLUEPULSE MEMBER 3 PIPELINE COMPLETED ===")
    for name, info in summary["scenarios"].items():
        risk = info["risk_summary"]
        anom = info["anomaly_summary"]
        print(
            f"- {name}: max_risk={risk['network_max_risk_score']}/100, "
            f"status={risk['network_highest_status']}, alerts={anom['total_alerts']}"
        )
