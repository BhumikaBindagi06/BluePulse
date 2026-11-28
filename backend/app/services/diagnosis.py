"""Diagnosis orchestration service."""

from bluepulse_contracts import DiagnosisResult, EvidenceItem


class DiagnosisService:
    """Synthesizes structured diagnoses from normalized evidence items."""

    def diagnose(
        self,
        diagnosis_id: str,
        evidence: list[EvidenceItem],
    ) -> DiagnosisResult:
        """Produce a baseline diagnosis summary from collected evidence."""
        if not evidence:
            return DiagnosisResult(
                diagnosis_id=diagnosis_id,
                summary="Insufficient evidence to form a diagnosis.",
                confidence=0.0,
                evidence_ids=[],
            )

        return DiagnosisResult(
            diagnosis_id=diagnosis_id,
            summary=f"Evaluated {len(evidence)} evidence item(s).",
            confidence=0.5,
            evidence_ids=[item.id for item in evidence],
        )

