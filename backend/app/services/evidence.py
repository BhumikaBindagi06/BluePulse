"""Evidence collection and normalization service."""

from bluepulse_contracts import EvidenceItem


class EvidenceService:
    """Collects and normalizes evidence items for downstream diagnosis."""

    def collect(self, source: str, raw_records: list[dict[str, object]]) -> list[EvidenceItem]:
        """Convert raw module records into validated EvidenceItem contracts."""
        items: list[EvidenceItem] = []
        for idx, record in enumerate(raw_records, start=1):
            item_id = str(record.get("id") or f"{source}-{idx}")
            summary = str(record.get("summary") or "No summary provided")
            items.append(
                EvidenceItem(
                    id=item_id,
                    source=source,
                    summary=summary,
                    metadata=dict(record),
                )
            )
        return items

