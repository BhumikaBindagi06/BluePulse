"""Impact assessment service."""

from bluepulse_contracts import DiagnosisResult, ImpactAssessment


class ImpactService:
    """Evaluates operational and system impact from a diagnosis result."""

    def assess(
        self,
        impact_id: str,
        diagnosis: DiagnosisResult,
        affected_components: list[str] | None = None,
    ) -> ImpactAssessment:
        """Compute a baseline impact assessment for a diagnosis."""
        severity = "medium" if diagnosis.confidence >= 0.5 else "low"
        return ImpactAssessment(
            impact_id=impact_id,
            severity=severity,
            affected_components=affected_components or [],
            summary=f"Impact assessment for {diagnosis.diagnosis_id}: {diagnosis.summary}",
        )

