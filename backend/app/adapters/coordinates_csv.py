"""D11: team-controlled coordinate table (CSV).

Accepts the file as written by 'geocode-review' (UTF-8 with BOM, ';'), plain UTF-8 with ','
and as saved again by Excel with Croatian regional settings (';', decimal comma,
Windows-1250, dates as 27.10.2026.).

Columns: space_id, lon, lat, precision_status, evidence_url, evidence_note, checked_at
(extra columns such as the template's auto_note are ignored)
- precision_status: entrance_confirmed | building_approximate | needs_review | missing
- confirmed/approximate rows need lon/lat inside Zagreb and evidence (URL or note)
- needs_review/missing rows must not carry coordinates (status left unchanged by mistake)
- checked_at: ISO date or datetime; never in the future (FZ31)
"""

import csv
import io
import re
from datetime import UTC, datetime

from app.adapters.geojson_points import ZAGREB_BBOX
from app.adapters.parsing import ParseResult
from app.adapters.registry import SourceSpec
from app.adapters.spaces_csv import record_sha256

REQUIRED = (
    "space_id",
    "lon",
    "lat",
    "precision_status",
    "evidence_url",
    "evidence_note",
    "checked_at",
)
PRECISIONS = {"entrance_confirmed", "building_approximate", "needs_review", "missing"}
HEADER_LINE = ",".join(REQUIRED)


_HR_DATE = re.compile(r"^(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\.?(?:\s+(\d{1,2}):(\d{2}))?$")


def _parse_checked_at(value: str) -> datetime:
    text = value.strip()
    hr = _HR_DATE.match(text)
    if hr:
        day, month, year, hour, minute = hr.groups()
        return datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=UTC
        )
    ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def parse_coordinates_csv(content: bytes, spec: SourceSpec) -> ParseResult:
    del spec  # the format is fixed by this module, not by the registry
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

    minx, miny, maxx, maxy = ZAGREB_BBOX
    now = datetime.now(UTC)
    seen: set[str] = set()
    unfilled = 0
    for line_no, row in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if not any(row.values()):
            continue
        space_id = row["space_id"]
        if not space_id.isdigit():
            result.block("field_invalid", f"Redak {line_no}: space_id mora biti broj.")
            continue
        if space_id in seen:
            result.block("duplicate_id", f"Prostor {space_id} se ponavlja.", space_id)
            continue
        seen.add(space_id)
        precision = row["precision_status"]
        if precision in {"needs_review", "missing"} and not row["checked_at"]:
            # Unfilled row from the 'geocode-review' template: nothing to record yet.
            unfilled += 1
            continue
        if precision not in PRECISIONS:
            result.block("field_invalid", f"Redak {line_no}: nepoznat precision_status.", space_id)
            continue
        if precision in {"needs_review", "missing"} and (row["lon"] or row["lat"]):
            # Coordinates were checked but the status was left as in the template; dropping
            # them silently would lose the team's work.
            result.block(
                "field_invalid",
                f"Redak {line_no}: upisane su koordinate, a precision_status je {precision}. "
                "Upiši entrance_confirmed ili building_approximate.",
                space_id,
            )
            continue
        try:
            checked_at = _parse_checked_at(row["checked_at"])
        except ValueError:
            result.block("field_invalid", f"Redak {line_no}: checked_at nije datum.", space_id)
            continue
        if checked_at > now:
            result.block("field_invalid", f"Redak {line_no}: checked_at je u budućnosti.", space_id)
            continue

        lon = lat = None
        if precision in {"entrance_confirmed", "building_approximate"}:
            try:
                lon = float(row["lon"].replace(",", "."))
                lat = float(row["lat"].replace(",", "."))
            except ValueError:
                result.block("field_invalid", f"Redak {line_no}: lon/lat nisu brojevi.", space_id)
                continue
            if minx <= lat <= maxx and miny <= lon <= maxy:
                result.block("axis_swapped", f"Redak {line_no}: zamijenjeni lon i lat.", space_id)
                continue
            if not (minx <= lon <= maxx and miny <= lat <= maxy):
                result.block("field_invalid", f"Redak {line_no}: točka je izvan Zagreba.", space_id)
                continue
            if not (row["evidence_url"] or row["evidence_note"]):
                result.block(
                    "field_invalid", f"Redak {line_no}: potvrđena točka treba dokaz.", space_id
                )
                continue
        result.records.append(
            {
                "space_id": space_id,
                "lon": lon,
                "lat": lat,
                "precision_status": precision,
                "evidence_url": row["evidence_url"] or None,
                "evidence_note": row["evidence_note"] or None,
                "checked_at": checked_at,
                "raw": row,
                "sha256": record_sha256(row),
            }
        )
    if unfilled:
        result.warn("rows_unfilled", f"Preskočeno neispunjenih redaka: {unfilled}.")
    if not result.records and not result.blocking:
        result.block("empty_source", "Tablica koordinata nema nijedan ispunjen redak.")
    return result
