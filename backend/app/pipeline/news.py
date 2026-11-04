"""Notice proposals and their human review (ADR24, FZ13-FZ17).

news-classify        new notice revisions -> ai_result + pending_review context_card
news-review-template ';' CSV of pending cards, with the source text, for a team member
import-news-review   decisions da/ne with reviewer initials; only pending rows change

A public card always comes through import-news-review. Nothing here changes a score.
"""

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Engine, text

from app.ai import news
from app.ai.model import Embedder, config_sha256
from app.gis.district_names import mentioned_districts
from app.pipeline.description_tags import _AUTOMATED, _DECISION

REVIEW_HEADER = (
    "card_id",
    "decision",
    "reviewer",
    "review_note",
    "summary",
    "location_label",
    "district_ids",
    "valid_from",
    "valid_to",
    "topic",
    "similarity",
    "title",
    "url",
    "text",
)
_EXCERPT = 1500


def _district_rows(conn: Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        text(
            """
            SELECT d.district_id, d.name
            FROM prostoriq.district d
            JOIN prostoriq.bundle_source b ON b.source_version_id = d.source_version_id
            JOIN prostoriq.active_dataset a ON a.dataset_bundle_id = b.dataset_bundle_id
            ORDER BY d.name
            """
        )
    ).all()
    return [(str(r[0]), str(r[1])) for r in rows]


def _streets(conn: Connection) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT o.street FROM prostoriq.osm_address o
            JOIN prostoriq.bundle_source b ON b.source_version_id = o.source_version_id
            JOIN prostoriq.active_dataset a ON a.dataset_bundle_id = b.dataset_bundle_id
            """
        )
    ).all()
    return [str(r[0]) for r in rows]


def _street_location(conn: Connection, street: str) -> tuple[list[str], str | None]:
    """Districts that contain the street's address points, and its centre as WKT."""
    row = conn.execute(
        text(
            """
            WITH points AS (
                SELECT o.geom FROM prostoriq.osm_address o
                JOIN prostoriq.bundle_source b ON b.source_version_id = o.source_version_id
                JOIN prostoriq.active_dataset a ON a.dataset_bundle_id = b.dataset_bundle_id
                WHERE o.street = :s
            )
            SELECT ST_AsText(ST_Centroid(ST_Collect(p.geom))),
                   (SELECT array_agg(DISTINCT d.district_id)
                    FROM prostoriq.district d
                    JOIN prostoriq.bundle_source b ON b.source_version_id = d.source_version_id
                    JOIN prostoriq.active_dataset a ON a.dataset_bundle_id = b.dataset_bundle_id
                    JOIN points q ON ST_Covers(d.geom, q.geom))
            FROM points p
            """
        ),
        {"s": street},
    ).one()
    return [str(x) for x in (row[1] or [])], row[0]


def _start_job(conn: Connection, count: int) -> str:
    key = f"news-classify-{uuid.uuid4()}"
    body = json.dumps({"action": "news-classify", "revisions": count})
    return str(
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.import_job (source_code, kind, status, idempotency_key,
                    request_sha256, request_json, started_at, attempt)
                VALUES ('D09', 'ai_process', 'running', :k, encode(sha256(:b), 'hex'),
                    CAST(:j AS jsonb), now(), 1)
                RETURNING job_id::text
                """
            ),
            {"k": key, "b": body.encode(), "j": body},
        ).scalar_one()
    )


def classify_notices(engine: Engine, embedder: Embedder, config: dict[str, Any]) -> dict[str, int]:
    """Propose cards for notice revisions this model and configuration have not seen yet."""
    digest = config_sha256(config)
    counts = {"revisions": 0, "classified": 0, "uncertain": 0, "irrelevant": 0, "cards": 0}
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT r.notice_revision_id::text AS id, r.notice_id::text AS notice_id,
                           r.title, r.clean_text, r.published_date
                    FROM prostoriq.notice_revision r
                    WHERE NOT EXISTS (
                        SELECT 1 FROM prostoriq.ai_result x
                        WHERE x.notice_revision_id = r.notice_revision_id
                          AND x.model_revision = :m AND x.config_sha256 = :c
                          AND x.pipeline_version = :p)
                    ORDER BY r.notice_revision_id
                    """
                ),
                {"m": config["model_revision"], "c": digest, "p": news.PIPELINE_VERSION},
            )
            .mappings()
            .all()
        )
        if not rows:
            return counts
        job_id = _start_job(conn, len(rows))
        districts = _district_rows(conn)
        streets = _streets(conn)
        for row in rows:
            counts["revisions"] += 1
            body = str(row["clean_text"])
            title = str(row["title"])
            chunks = news.content_chunks(
                body,
                embedder.tokenizer,
                int(config["content_chunk_tokens"]),
                int(config["overlap_tokens"]),
            )
            result = news.classify(
                title,
                chunks,
                embedder,
                config["topics"],
                float(config["topic_min_similarity"]),
                float(config["topic_min_margin"]),
            )
            counts[result.status] += 1
            source = f"{title}\n{body}"
            named = mentioned_districts(source, districts)
            # A street in the title is what the notice is about; the body also lists detours.
            found_streets = news.mentioned_streets(title, streets) or news.mentioned_streets(
                body, streets
            )
            published: date | None = row["published_date"]
            window = news.validity_window(news.extract_dates(body), published)
            evidence = {
                "districts": [{"district_id": d, "words": w} for d, w in named],
                "streets": found_streets,
            }
            ai_result_id = conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.ai_result (notice_revision_id, job_id, model_id,
                        model_revision, config_sha256, pipeline_version, topic, status,
                        topic_scores, profile_scores, evidence_spans)
                    VALUES (CAST(:r AS uuid), CAST(:j AS uuid), :mid, :mrev, :c, :p, :t, :s,
                        CAST(:ts AS jsonb), '{}'::jsonb, CAST(:ev AS jsonb))
                    RETURNING ai_result_id::text
                    """
                ),
                {
                    "r": row["id"],
                    "j": job_id,
                    "mid": config["model_id"],
                    "mrev": config["model_revision"],
                    "c": digest,
                    "p": news.PIPELINE_VERSION,
                    "t": result.topic,
                    "s": result.status,
                    "ts": json.dumps({**result.scores, "margin": result.margin}),
                    "ev": json.dumps(evidence, ensure_ascii=False),
                },
            ).scalar_one()
            # A changed text sends earlier cards of the same notice back to review (ADR11).
            conn.execute(
                text(
                    """
                    UPDATE prostoriq.context_card c SET status = 'needs_review',
                        version = c.version + 1
                    FROM prostoriq.notice_revision r
                    WHERE c.notice_revision_id = r.notice_revision_id
                      AND r.notice_id = CAST(:n AS uuid)
                      AND r.notice_revision_id <> CAST(:r AS uuid)
                      AND c.status = 'approved'
                    """
                ),
                {"n": row["notice_id"], "r": row["id"]},
            )
            if result.status != "classified" or result.topic is None:
                continue
            label, kind, ids, geom = _location(conn, named, found_streets, districts)
            conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.context_card (ai_result_id, notice_revision_id, topic,
                        profile_codes, summary, location_kind, location_label, location_geom,
                        district_ids, location_evidence, valid_from, valid_to, review_due_at)
                    VALUES (CAST(:a AS uuid), CAST(:r AS uuid), :t, CAST(:pc AS jsonb), :sum, :k,
                        :l, ST_GeomFromText(:g, 4326), CAST(:d AS jsonb), CAST(:e AS jsonb),
                        :vf, :vt, :due)
                    """
                ),
                {
                    "a": ai_result_id,
                    "r": row["id"],
                    "t": result.topic,
                    "pc": json.dumps(config["topic_profiles"][result.topic]),
                    "sum": news.template_summary(title, label, window),
                    "k": kind,
                    "l": label,
                    "g": geom,
                    "d": json.dumps(ids),
                    "e": json.dumps(evidence, ensure_ascii=False),
                    "vf": window[0] if window else None,
                    "vt": window[1] if window else None,
                    "due": None,
                },
            )
            counts["cards"] += 1
        conn.execute(
            text(
                """
                UPDATE prostoriq.import_job SET status = 'succeeded', finished_at = now(),
                    accepted_count = :n, report = CAST(:rep AS jsonb)
                WHERE job_id = CAST(:j AS uuid)
                """
            ),
            {"n": counts["revisions"], "rep": json.dumps(counts), "j": job_id},
        )
    return counts


def _location(
    conn: Connection,
    named: list[tuple[str, str]],
    streets: list[str],
    districts: list[tuple[str, str]],
) -> tuple[str | None, str | None, list[str], str | None]:
    if streets:
        ids, geom = _street_location(conn, streets[0])
        if ids:
            return streets[0], "street", ids, geom
    if named:
        names = dict(districts)
        ids = [d for d, _ in named]
        return ", ".join(names[d] for d in ids), "district", ids, None
    return None, None, [], None


def review_template_csv(engine: Engine) -> str:
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT c.card_id::text AS card_id, c.summary, c.location_label, c.district_ids,
                           c.valid_from, c.valid_to, c.topic, x.topic_scores, r.title, r.clean_text,
                           n.canonical_url
                    FROM prostoriq.context_card c
                    JOIN prostoriq.ai_result x ON x.ai_result_id = c.ai_result_id
                    JOIN prostoriq.notice_revision r
                        ON r.notice_revision_id = c.notice_revision_id
                    JOIN prostoriq.notice n ON n.notice_id = r.notice_id
                    WHERE c.status IN ('pending_review', 'needs_review')
                    ORDER BY c.created_at, c.card_id
                    """
                )
            )
            .mappings()
            .all()
        )
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(REVIEW_HEADER)
    for r in rows:
        writer.writerow(
            [
                r["card_id"],
                "",
                "",
                "",
                r["summary"],
                r["location_label"] or "",
                " ".join(r["district_ids"] or []),
                r["valid_from"].isoformat() if r["valid_from"] else "",
                r["valid_to"].isoformat() if r["valid_to"] else "",
                r["topic"],
                r["topic_scores"].get(r["topic"], ""),
                r["title"],
                r["canonical_url"],
                " ".join(str(r["clean_text"]).split())[:_EXCERPT],
            ]
        )
    return out.getvalue()


@dataclass
class ReviewOutcome:
    approved: int = 0
    rejected: int = 0
    skipped_empty: int = 0
    not_pending: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Decision:
    card_id: str
    status: str
    reviewer: str
    note: str | None
    summary: str
    label: str | None
    district_ids: list[str]
    valid_from: datetime | None
    valid_to: datetime | None


def _when(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_row(line_no: int, row: dict[str, str], known: set[str]) -> _Decision | str:
    status = _DECISION.get(row.get("decision", "").lower())
    reviewer = row.get("reviewer", "")
    try:
        card_id = str(uuid.UUID(row.get("card_id", "")))
    except ValueError:
        return f"Redak {line_no}: card_id nije valjan."
    if status is None:
        return f"Redak {line_no}: decision mora biti da ili ne."
    if not 2 <= len(reviewer) <= 40:
        return f"Redak {line_no}: upiši inicijale u reviewer (2-40 znakova)."
    if _AUTOMATED.search(reviewer):
        return f"Redak {line_no}: reviewer mora biti osoba iz tima, ne AI ({reviewer})."
    note = row.get("review_note") or None
    if note is not None and len(note) > 500:
        return f"Redak {line_no}: review_note je dulji od 500 znakova."
    try:
        valid_from, valid_to = _when(row.get("valid_from", "")), _when(row.get("valid_to", ""))
    except ValueError:
        return f"Redak {line_no}: valid_from ili valid_to nije ISO datum."
    ids = row.get("district_ids", "").split()
    summary = row.get("summary", "")
    label = row.get("location_label") or None
    if status == "approved":
        if not summary or len(summary.split()) > 60:
            return f"Redak {line_no}: summary mora imati od 1 do 60 riječi."
        if not label or not ids:
            return f"Redak {line_no}: za odobrenje upiši location_label i district_ids."
        if unknown := [d for d in ids if d not in known]:
            return f"Redak {line_no}: nepoznata četvrt {', '.join(unknown)}."
        if valid_from and valid_to and valid_to <= valid_from:
            return f"Redak {line_no}: valid_to mora biti nakon valid_from."
    return _Decision(card_id, status, reviewer, note, summary, label, ids, valid_from, valid_to)


def import_review(
    engine: Engine, content: bytes, *, review_days: int = 30, now: datetime | None = None
) -> ReviewOutcome:
    """Apply decisions. Nothing is written if any filled row is invalid."""
    try:
        body = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        body = content.decode("cp1250", errors="replace")
    first = body.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(body), delimiter=";" if ";" in first else ",")
    outcome = ReviewOutcome()
    with engine.connect() as conn:
        known = {d for d, _ in _district_rows(conn)}
    decisions: list[_Decision] = []
    for line_no, raw in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if not row.get("decision"):
            outcome.skipped_empty += 1
            continue
        parsed = _parse_row(line_no, row, known)
        if isinstance(parsed, str):
            outcome.errors.append(parsed)
        else:
            decisions.append(parsed)
    if outcome.errors:
        return outcome
    moment = now or datetime.now(UTC)
    with engine.begin() as conn:
        for d in decisions:
            changed = conn.execute(
                text(
                    """
                    UPDATE prostoriq.context_card SET status = :st, version = version + 1,
                        summary = CASE WHEN :st = 'approved' THEN :sum ELSE summary END,
                        location_label = COALESCE(:label, location_label),
                        location_kind = COALESCE(location_kind,
                            CASE WHEN :label IS NOT NULL THEN 'area' END),
                        district_ids = CASE WHEN :st = 'approved' THEN CAST(:ids AS jsonb)
                            ELSE district_ids END,
                        valid_from = CASE WHEN :st = 'approved' THEN :vf ELSE valid_from END,
                        valid_to = CASE WHEN :st = 'approved' THEN :vt ELSE valid_to END,
                        review_due_at = CASE WHEN :st = 'approved' AND :vt IS NULL THEN :due
                            ELSE review_due_at END,
                        approved_at = CASE WHEN :st = 'approved' THEN :at END,
                        reviewed_by_name = :who
                    WHERE card_id = CAST(:id AS uuid)
                      AND status IN ('pending_review', 'needs_review')
                    """
                ),
                {
                    "st": d.status,
                    "sum": d.summary,
                    "label": d.label,
                    "ids": json.dumps(d.district_ids),
                    "vf": d.valid_from,
                    "vt": d.valid_to,
                    "due": moment + timedelta(days=review_days),
                    "at": moment,
                    "who": d.reviewer,
                    "id": d.card_id,
                },
            ).rowcount
            if not changed:
                outcome.not_pending += 1
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.audit_event (action, entity_type, entity_id, request_id,
                        after_value, reason)
                    VALUES ('review_context_card', 'context_card', :id, CAST(:rid AS uuid),
                        CAST(:after AS jsonb), :reason)
                    """
                ),
                {
                    "id": d.card_id,
                    "rid": str(uuid.uuid4()),
                    "after": json.dumps({"status": d.status, "reviewer": d.reviewer}),
                    "reason": d.note or "Pregled kartice",
                },
            )
            if d.status == "approved":
                outcome.approved += 1
            else:
                outcome.rejected += 1
    return outcome
