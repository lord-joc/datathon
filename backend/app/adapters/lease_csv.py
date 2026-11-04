"""D20: city register of lease contracts (CSV, Windows-1250, ';', decimal comma, ADR24).

The market signal is the monthly rent per m2 per activity. The register also names tenants,
often natural persons, in its own column and inside "Predmet ugovora". Parsing is therefore an
allowlist: only the premises ID, address, area, rent, signing date and the text after the word
"djelatnost" are kept. Names never reach the database or the API.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.adapters.parsing import ParseResult
from app.adapters.registry import SourceSpec
from app.adapters.spaces_csv import record_sha256

MAX_HEADER_SEARCH_ROWS = 6
_LEASE_TYPE = "ugovor o zakupu poslovnog prostora"
_SPACE_ID = re.compile(r"\bID\s*(\d{1,12})\b")
_AREA = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)\s*m\s*[2²]", re.IGNORECASE)
_ACTIVITY = re.compile(r"\bdjelatnost\w*\s+(.+)$", re.IGNORECASE | re.DOTALL)
_MAX_ACTIVITY = 300
_REQUIRED = ("ID", "Adresa", "Predmet ugovora", "Vrsta ugovora", "Status", "Valuta")
_RENT_PREFIX = "zakupnina/ naknada mjesečno"
_SIGNED_PREFIX = "datum potpisa"


def _norm(value: str) -> str:
    return " ".join(value.split())


def _number(value: str) -> Decimal | None:
    text = value.strip().replace(".", "").replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number > 0 else None


def _date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip().rstrip("."), "%d.%m.%Y").date()
    except ValueError:
        return None


def _street_part(address: str) -> str:
    """'ZAGREB,  MARTIĆEVA 0014' -> 'MARTIĆEVA 0014'."""
    return _norm(address.split(",", 1)[-1])


def parse_lease_csv(content: bytes, spec: SourceSpec) -> ParseResult:
    result = ParseResult()
    try:
        body = content.decode(spec.encoding or "cp1250")
    except (UnicodeDecodeError, LookupError):
        result.block("encoding_invalid", "Datoteka nije u očekivanom kodiranju.")
        return result
    rows = list(csv.reader(io.StringIO(body), delimiter=";"))

    header_index = None
    for index, row in enumerate(rows[:MAX_HEADER_SEARCH_ROWS]):
        names = [_norm(c) for c in row]
        if all(name in names for name in _REQUIRED):
            header_index = index
            break
    if header_index is None:
        result.block("schema_changed", "Zaglavlje registra ugovora nije prepoznato.")
        return result

    columns = {_norm(c).casefold(): i for i, c in enumerate(rows[header_index])}
    rent_col = next((i for n, i in columns.items() if n.startswith(_RENT_PREFIX)), None)
    signed_col = next((i for n, i in columns.items() if n.startswith(_SIGNED_PREFIX)), None)
    if rent_col is None or signed_col is None:
        result.block("schema_changed", "Nedostaje stupac zakupnine ili datuma potpisa.")
        return result

    def cell(row: list[str], name: str) -> str:
        i = columns[name.casefold()]
        return _norm(row[i]) if i < len(row) else ""

    seen: set[str] = set()
    for row in rows[header_index + 1 :]:
        key = cell(row, "ID")
        if not key.isdigit():
            continue
        if key in seen:
            result.block("duplicate_id", f"Ugovor {key} se ponavlja.", key)
            continue
        seen.add(key)
        if cell(row, "Vrsta ugovora").casefold() != _LEASE_TYPE:
            continue
        if cell(row, "Status").casefold() != "aktivan ugovor" or cell(row, "Valuta") != "EUR":
            continue
        rent = _number(row[rent_col]) if rent_col < len(row) else None
        subject = cell(row, "Predmet ugovora")
        area = _AREA.search(subject)
        activity = _ACTIVITY.search(subject)
        area_m2 = _number(area.group(1)) if area else None
        if rent is None or area_m2 is None or activity is None:
            # No rent, area or activity: not usable as a market signal, and not an error.
            result.warn("lease_incomplete", "Ugovor nema zakupninu, površinu ili djelatnost.", key)
            continue
        space = _SPACE_ID.search(subject)
        signed = _date(row[signed_col]) if signed_col < len(row) else None
        kept = {
            "contract_key": key,
            "space_id": space.group(1) if space else None,
            "address": _street_part(cell(row, "Adresa")),
            "area_m2": str(area_m2),
            "monthly_rent_eur": str(rent),
            "signed_date": signed.isoformat() if signed else None,
            "activity": _norm(activity.group(1))[:_MAX_ACTIVITY],
        }
        result.records.append(
            {**kept, "sha256": record_sha256({k: str(v) for k, v in kept.items()})}
        )
    if not result.records and not result.blocking:
        result.block("no_records", "U registru nema nijednog upotrebljivog ugovora o zakupu.")
    return result
