"""D01/D02: city list of vacant business premises (CSV, Windows-1250, ';', decimal comma).

The header is not on the first line (D01: 2nd logical row, D02: 3rd), so the parser looks
for the row that contains the registry's source fields instead of assuming a position.
Values are never "repaired": an invalid area or ID is an error, not a guess (TI01).
"""

import csv
import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.parsing import ParseResult
from app.adapters.registry import SourceSpec

MAX_HEADER_SEARCH_ROWS = 6
_DIGITS = re.compile(r"^[0-9]+$")
_AREA = re.compile(r"^[0-9]{1,3}(\.?[0-9]{3})*(,[0-9]+)?$|^[0-9]+(,[0-9]+)?$")


def _norm_header(value: str) -> str:
    return " ".join(value.replace("﻿", "").split()).casefold()


def _normalize_ws(value: str) -> str:
    return " ".join(value.split())


def parse_area(value: str) -> Decimal | None:
    """'87,96' -> 87.96; '1.234,50' -> 1234.50. Empty -> None. Anything else -> ValueError."""
    text = value.strip()
    if not text:
        return None
    if not _AREA.match(text):
        raise ValueError(f"neispravan zapis površine: {text!r}")
    try:
        number = Decimal(text.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:  # pragma: no cover - regex already guards this
        raise ValueError(f"neispravan zapis površine: {text!r}") from exc
    if number <= 0:
        raise ValueError(f"površina mora biti veća od 0: {text!r}")
    return number.quantize(Decimal("0.01"))


def parse_position(value: str) -> str | None:
    text = _normalize_ws(value)
    if not text:
        return None
    return "street" if text.casefold() == "ulični".casefold() else "other"


def record_sha256(raw: dict[str, str]) -> str:
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_spaces_csv(content: bytes, spec: SourceSpec) -> ParseResult:
    result = ParseResult()
    encoding = "cp1250" if (spec.encoding or "").lower().startswith("windows-1250") else "utf-8"
    try:
        text = content.decode(encoding)
    except UnicodeDecodeError as exc:
        result.block("encoding_invalid", f"Datoteka nije valjan {encoding}: bajt {exc.start}.")
        return result

    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))
    fields = {target: spec.source_field(target) for target in _TARGETS}
    required = [f for f in (fields["space.space_id"], fields["space_revision.address"]) if f]
    if len(required) < 2:
        result.block("registry_mapping_missing", f"Registar za {spec.code} nema ID i ADRESA.")
        return result

    header_index = _find_header(rows, required)
    if header_index is None:
        result.block(
            "schema_changed",
            f"Zaglavlje s poljima {', '.join(required)} nije pronađeno u prvih "
            f"{MAX_HEADER_SEARCH_ROWS} redaka.",
        )
        return result

    header = [_norm_header(h) for h in rows[header_index]]
    expected = [f for f in fields.values() if f and not f.startswith("constant")]
    missing = [f for f in expected if _norm_header(f) not in header]
    if missing:
        result.block("schema_changed", f"Nedostaju stupci: {', '.join(missing)}.")
        return result
    col = {f: header.index(_norm_header(f)) for f in expected}

    seen: set[str] = set()
    for line_no, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(cell.strip() for cell in row):
            continue
        raw = {
            rows[header_index][i].strip(): (row[i] if i < len(row) else "")
            for i in range(len(header))
        }
        key_field = fields["space.space_id"]
        assert key_field is not None
        space_id = row[col[key_field]].strip() if col[key_field] < len(row) else ""
        if not _DIGITS.match(space_id):
            result.block("field_invalid", f"Redak {line_no}: ID nije broj.", None, key_field)
            continue
        if space_id in seen:
            result.block("duplicate_id", f"ID {space_id} se ponavlja.", space_id, key_field)
            continue
        seen.add(space_id)

        record: dict[str, Any] = {"space_id": space_id, "raw": raw, "sha256": record_sha256(raw)}
        address_field = fields["space_revision.address"]
        assert address_field is not None
        address = row[col[address_field]].strip()
        if not address:
            result.block("field_invalid", "Adresa je prazna.", space_id, address_field)
            continue
        record["address"] = address

        district_field = fields["space_revision.district_name_source"]
        record["district_name_source"] = (
            _normalize_ws(row[col[district_field]]) or None if district_field else None
        )

        area_field = fields["space_revision.area_m2"]
        if area_field:
            try:
                record["area_m2"] = parse_area(row[col[area_field]])
            except ValueError as exc:
                result.block("field_invalid", str(exc), space_id, area_field)
                continue
            if record["area_m2"] is None:
                result.warn("area_missing", "Površina nije navedena.", space_id, area_field)
        else:
            record["area_m2"] = None

        position_field = fields["space_revision.position_code"]
        position_raw = _normalize_ws(row[col[position_field]]) if position_field else ""
        record["position_code"] = parse_position(position_raw)
        record["position_source"] = position_raw or None

        desc_field = fields["space_revision.structure_description"]
        record["structure_description"] = (
            _normalize_ws(row[col[desc_field]]) or None if desc_field else None
        )
        usage_field = fields["space_revision.usage_code_source"]
        record["usage_code_source"] = row[col[usage_field]].strip() or None if usage_field else None
        record["inventory_kind"] = "unfit" if spec.code == "D02" else "regular"
        result.records.append(record)

    if not result.records and not result.blocking:
        result.block("empty_source", "Datoteka nema nijedan zapis prostora.")
    return result


_TARGETS = (
    "space.space_id",
    "space_revision.district_name_source",
    "space_revision.address",
    "space_revision.area_m2",
    "space_revision.position_code",
    "space_revision.structure_description",
    "space_revision.usage_code_source",
)


def _find_header(rows: list[list[str]], required: list[str]) -> int | None:
    wanted = {_norm_header(r) for r in required}
    for index, row in enumerate(rows[:MAX_HEADER_SEARCH_ROWS]):
        if wanted <= {_norm_header(c) for c in row}:
            return index
    return None
