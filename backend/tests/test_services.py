"""Tests for integration services and shared contracts."""

from app.services.diagnosis import DiagnosisService
from app.services.evidence import EvidenceService
from app.services.impact import ImpactService


def test_evidence_diagnosis_impact_pipeline() -> None:
    """Services produce valid contract models across the integration pipeline."""
    evidence_svc = EvidenceService()
    diagnosis_svc = DiagnosisService()
    impact_svc = ImpactService()

    evidence = evidence_svc.collect(
        source="sample",
        raw_records=[{"id": "ev-1", "summary": "Elevated turbidity detected"}],
    )
    assert len(evidence) == 1
    assert evidence[0].id == "ev-1"

    diagnosis = diagnosis_svc.diagnose(diagnosis_id="diag-1", evidence=evidence)
    assert diagnosis.confidence == 0.5
    assert diagnosis.evidence_ids == ["ev-1"]

    impact = impact_svc.assess(
        impact_id="imp-1",
        diagnosis=diagnosis,
        affected_components=["sensor-grid"],
    )
    assert impact.severity == "medium"
    assert impact.affected_components == ["sensor-grid"]


def test_diagnosis_without_evidence() -> None:
    """DiagnosisService handles empty evidence gracefully."""
    diagnosis_svc = DiagnosisService()
    diagnosis = diagnosis_svc.diagnose(diagnosis_id="diag-empty", evidence=[])
    assert diagnosis.confidence == 0.0
    assert diagnosis.evidence_ids == []

