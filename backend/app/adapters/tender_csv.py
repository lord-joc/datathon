"""D12: team table of rents and conditions from the City of Zagreb tenders (CSV).

One row per space (or per space and profile) as read from an official tender on zagreb.hr.
Same file conventions as D11: UTF-8 with BOM or Windows-1250 from Excel, ';' or ',', decimal
comma and Croatian dates are accepted.

Columns: space_id, monthly_rent_eur, tender_url, checked_at (required)
         profile, tender_active, physical_vacancy, activity_allowed, technical_suitable,
         evidence_note (optional; extra columns are ignored)
- monthly_rent_eur: the starting monthly rent stated in the tender for this space (EUR).
  Never an estimate; leave it empty when the tender does not state it.
- tender_url: https link on zagreb.hr to the tender document or page (the evidence).
- profile: empty = the row applies to every business profile.
- conditions: yes / no / unknown (also da / ne / nepoznato); empty = unknown.
- checked_at: when the team read the tender; never in the future.
"""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from app.adapters.coordinates_csv import _parse_checked_at
from app.adapters.parsing import ParseResult
from app.adapters.registry import SourceSpec
from app.adapters.spaces_csv import record_sha256

REQUIRED = ("space_id", "monthly_rent_eur", "tender_url", "checked_at")
CONDITIONS = ("tender_active", "physical_vacancy", "activity_allowed", "technical_suitable")
PROFILES = ("cafe", "office", "retail", "food_takeaway", "personal_care", "education", "workshop")
ALLOWED_HOSTS = {"zagreb.hr", "www.zagreb.hr"}
MAX_RENT = Decimal("1000000")
COST_DEFINITION = "tender_start_monthly_v1"
_TRI = {
    "": "unknown",
    "yes": "yes",
    "da": "yes",
    "no": "no",
    "ne": "no",
    "unknown": "unknown",
    "nepoznato": "unknown",
}


def _rent(value: str) -> Decimal | None:
    text = value.replace("€", "").replace("EUR", "").replace(" ", "").strip()
    if not text:
        return None
    # "1.234,56" (Croatian Excel) and "1234.56" both mean the same amount.
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return Decimal(text)


def parse_tender_csv(content: bytes, spec: SourceSpec) -> ParseResult:
    del spec  # the format is fixed by this module
    result = ParseResult()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1250", errors="replace")
        result.warn("encoding_cp1250", "Datoteka nije UTF-8; čitana kao Windows-1250 (Excel).")
    first_line = text.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        result.block("schema_changed", f"Nedostaju stupci: {', '.join(missing)}.")
        return result

    now = datetime.now(UTC)
    seen: set[tuple[str, str]] = set()
    unfilled = 0
    for line_no, raw in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue
        space_id = row["space_id"]
        if not space_id.isdigit():
            result.block("field_invalid", f"Redak {line_no}: space_id mora biti broj.")
            continue
        if not (
            row["monthly_rent_eur"] or row["tender_url"] or any(row.get(c) for c in CONDITIONS)
        ):
            # Untouched row from the 'tender-template' file.
            unfilled += 1
            continue
        profile = row.get("profile", "")
        if profile and profile not in PROFILES:
            result.block(
                "field_invalid", f"Redak {line_no}: nepoznat profil '{profile}'.", space_id
            )
            continue
        url = urlsplit(row["tender_url"])
        if url.scheme != "https" or (url.hostname or "") not in ALLOWED_HOSTS:
            result.block(
                "field_invalid",
                f"Redak {line_no}: tender_url mora biti https poveznica na zagreb.hr.",
                space_id,
            )
            continue
        try:
            rent = _rent(row["monthly_rent_eur"])
        except InvalidOperation:
            result.block(
                "field_invalid", f"Redak {line_no}: monthly_rent_eur nije iznos.", space_id
            )
            continue
        if rent is not None and not (Decimal(0) < rent <= MAX_RENT):
            result.block(
                "field_invalid", f"Redak {line_no}: zakupnina mora biti veća od 0 €.", space_id
            )
            continue
        conditions: dict[str, str] = {}
        for c in CONDITIONS:
            value = _TRI.get(row.get(c, "").lower())
            if value is None:
                result.block(
                    "field_invalid",
                    f"Redak {line_no}: {c} mora biti yes, no ili unknown.",
                    space_id,
                )
                break
            conditions[c] = value
        else:
            try:
                checked_at = _parse_checked_at(row["checked_at"])
            except ValueError:
                result.block("field_invalid", f"Redak {line_no}: checked_at nije datum.", space_id)
                continue
            if checked_at > now:
                result.block(
                    "field_invalid", f"Redak {line_no}: checked_at je u budućnosti.", space_id
                )
                continue
            if rent is None and all(v == "unknown" for v in conditions.values()):
                result.warn(
                    "rows_unfilled", f"Redak {line_no}: nema ni zakupnine ni uvjeta.", space_id
                )
                continue
            targets = (profile,) if profile else PROFILES
            duplicate = [p for p in targets if (space_id, p) in seen]
            if duplicate:
                result.block(
                    "duplicate_id",
                    f"Prostor {space_id} se ponavlja za profil {duplicate[0]}.",
                    space_id,
                )
                continue
            for p in targets:
                seen.add((space_id, p))
                result.records.append(
                    {
                        "space_id": space_id,
                        "profile": p,
                        **conditions,
                        "monthly_rent_eur": rent,
                        "tender_url": row["tender_url"],
                        "evidence_note": row.get("evidence_note") or None,
                        "checked_at": checked_at,
                        "raw": row,
                        "sha256": record_sha256(row),
                    }
                )
    if unfilled:
        result.warn("rows_unfilled", f"Preskočeno neispunjenih redaka: {unfilled}.")
    if not result.records and not result.blocking:
        result.block("empty_source", "Tablica natječaja nema nijedan ispunjen redak.")
    return result
