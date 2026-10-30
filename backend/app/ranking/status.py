"""Candidate status from the four mandatory conditions (FZ05, FZ06). No I/O.

- D02 (unfit inventory) is always excluded and never ranked.
- One confirmed 'no' -> excluded. All 'yes' -> ready. Otherwise conditional
  ("Potrebna provjera") with one reason per unconfirmed condition.
- A 'yes' is valid for at most 168 hours from checked_at (or until valid_until when that is
  earlier); after that it counts as 'unknown' with reason status_review_due.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

CONDITIONS = ("physical_vacancy", "tender_active", "activity_allowed", "technical_suitable")
_NOT_CONFIRMED = {
    "physical_vacancy": "vacancy_not_confirmed",
    "tender_active": "tender_not_confirmed",
    "activity_allowed": "activity_not_confirmed",
    "technical_suitable": "technical_not_confirmed",
}
_CONFIRMED_NO = {
    "physical_vacancy": "not_vacant",
    "tender_active": "no_active_tender",
    "activity_allowed": "activity_not_allowed",
    "technical_suitable": "technically_unsuitable",
}


@dataclass(frozen=True)
class Assessment:
    physical_vacancy: str = "unknown"
    tender_active: str = "unknown"
    activity_allowed: str = "unknown"
    technical_suitable: str = "unknown"
    checked_at: datetime | None = None
    valid_until: datetime | None = None
    evidence_url: str | None = None
    tender_url: str | None = None
    # D12: starting monthly rent stated in the tender (EUR); shown and compared, never scored.
    monthly_rent_eur: Decimal | None = None
    source_version_id: str | None = None
    # The team's note on the tender (title, publication date, item number).
    cost_note: str | None = None


def evaluate(
    inventory_kind: str,
    assessment: Assessment | None,
    *,
    now: datetime,
    validity_hours: int = 168,
) -> dict[str, Any]:
    """Status snapshot as stored with a ranking item and shown in the API."""
    a = assessment or Assessment()
    values = {c: getattr(a, c) for c in CONDITIONS}
    reasons: list[str] = []

    expires = None
    if a.checked_at is not None:
        expires = a.checked_at + timedelta(hours=validity_hours)
        if a.valid_until is not None:
            expires = min(expires, a.valid_until)
    if any(v == "yes" for v in values.values()) and (expires is None or now >= expires):
        values = {c: ("unknown" if v == "yes" else v) for c, v in values.items()}
        reasons.append("status_review_due")

    if inventory_kind == "unfit":
        status = "excluded"
        reasons.insert(0, "unfit_inventory")
    elif any(v == "no" for v in values.values()):
        status = "excluded"
        reasons += [_CONFIRMED_NO[c] for c in CONDITIONS if values[c] == "no"]
    elif all(v == "yes" for v in values.values()):
        status = "ready"
    else:
        status = "conditional"
        reasons += [_NOT_CONFIRMED[c] for c in CONDITIONS if values[c] == "unknown"]

    return {
        "inventory_kind": inventory_kind,
        **values,
        "candidate_status": status,
        "reasons": reasons,
        "checked_at": a.checked_at,
        "evidence_url": a.evidence_url,
        "tender_url": a.tender_url,
        "valid_until": a.valid_until,
        "evaluated_at": now,
    }
