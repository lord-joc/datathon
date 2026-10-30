"""D12 template: every regular space (D01) with address, district and area for the team."""

import csv
import io

from sqlalchemy import Engine, text

TEMPLATE_HEADER = (
    "space_id",
    "monthly_rent_eur",
    "tender_url",
    "checked_at",
    "profile",
    "tender_active",
    "physical_vacancy",
    "activity_allowed",
    "technical_suitable",
    "evidence_note",
    "address",
    "district",
    "area_m2",
)


def tender_template_csv(engine: Engine) -> str:
    """';' CSV that Excel with Croatian settings opens in columns; the last three are hints."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT r.space_id, r.address, r.district_name_source, r.area_m2
                FROM prostoriq.space_revision r
                WHERE r.source_version_id = (
                    SELECT source_version_id FROM prostoriq.source_version
                    WHERE source_code = 'D01' AND quality_status = 'valid'
                    ORDER BY fetched_at DESC LIMIT 1)
                ORDER BY r.space_id::bigint
                """
            )
        ).all()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(TEMPLATE_HEADER)
    for space_id, address, district, area in rows:
        area_text = "" if area is None else str(area).replace(".", ",")
        writer.writerow(
            [space_id, "", "", "", "", "", "", "", "", "", address, district or "", area_text]
        )
    return out.getvalue()
