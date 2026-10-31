"""Description tags for the active bundle and their human review (ADR21).

ai-tag-descriptions  rules -> pending_review rows (idempotent: an existing decision is kept)
tag-review-template  ';' CSV of pending tags, with the official text, for a team member
import-tag-review    decisions da/ne with reviewer initials; only pending rows change
"""

import csv
import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Engine, text

from app.ai import tags

REVIEW_HEADER = (
    "description_tag_id",
    "decision",
    "reviewer",
    "review_note",
    "space_id",
    "tag",
    "label",
    "value",
    "evidence",
    "description",
)
_DECISION = {"da": "approved", "yes": "approved", "ne": "rejected", "no": "rejected"}
# The public page says "potvrdio član tima"; a model's decision must never be recorded as one.
_AUTOMATED = re.compile(r"claude|gpt|gemini|copilot|\bai\b|\bbot\b|\bmodel", re.IGNORECASE)


def rules_sha256() -> str:
    body = json.dumps(
        {"labels": tags.TAG_LABELS, "rules": tags._RULES, "numbers": tags._NUMBERS},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def tag_descriptions(engine: Engine) -> dict[str, int]:
    """Propose tags for every regular space in the active bundle."""
    digest = rules_sha256()
    counts = {"spaces": 0, "proposed": 0, "already_known": 0}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT r.space_revision_id::text, r.space_id, r.structure_description
                FROM prostoriq.bundle_space b
                JOIN prostoriq.active_dataset a ON a.dataset_bundle_id = b.dataset_bundle_id
                JOIN prostoriq.space_revision r ON r.space_revision_id = b.space_revision_id
                WHERE r.inventory_kind = 'regular'
                ORDER BY r.space_id::bigint
                """
            )
        ).all()
        for revision_id, space_id, description in rows:
            counts["spaces"] += 1
            for proposal in tags.rule_tags(description or ""):
                inserted = conn.execute(
                    text(
                        """
                        INSERT INTO prostoriq.description_tag (space_revision_id, space_id, tag,
                            value, method, evidence, rules_sha256)
                        SELECT CAST(:r AS uuid), :s, :t, :v, :m, :e, :h
                        WHERE NOT EXISTS (
                            SELECT 1 FROM prostoriq.description_tag d
                            WHERE d.space_revision_id = CAST(:r AS uuid) AND d.tag = :t
                              AND d.value IS NOT DISTINCT FROM CAST(:v AS integer))
                        """
                    ),
                    {
                        "r": revision_id,
                        "s": space_id,
                        "t": proposal.tag,
                        "v": proposal.value,
                        "m": proposal.method,
                        "e": proposal.evidence[:500],
                        "h": digest,
                    },
                ).rowcount
                counts["proposed" if inserted else "already_known"] += 1
    return counts


def review_template_csv(engine: Engine) -> str:
    """Pending tags with the official description, so the reviewer reads the source itself."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT d.description_tag_id::text, d.space_id, d.tag, d.value, d.evidence,
                       r.structure_description
                FROM prostoriq.description_tag d
                JOIN prostoriq.space_revision r ON r.space_revision_id = d.space_revision_id
                WHERE d.status = 'pending_review'
                ORDER BY d.space_id::bigint, d.tag
                """
            )
        ).all()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(REVIEW_HEADER)
    for tag_id, space_id, tag, value, evidence, description in rows:
        writer.writerow(
            [
                tag_id,
                "",
                "",
                "",
                space_id,
                tag,
                tags.TAG_LABELS[tag],
                "" if value is None else value,
                evidence,
                description or "",
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


def import_review(engine: Engine, content: bytes) -> ReviewOutcome:
    """Apply da/ne decisions. Nothing is written if any filled row is invalid."""
    try:
        body = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        body = content.decode("cp1250", errors="replace")
    first = body.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(body), delimiter=";" if ";" in first else ",")
    outcome = ReviewOutcome()
    decisions: list[tuple[str, str, str, str | None]] = []
    for line_no, raw in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        decision = row.get("decision", "").lower()
        if not decision:
            outcome.skipped_empty += 1
            continue
        status = _DECISION.get(decision)
        reviewer = row.get("reviewer", "")
        note = row.get("review_note") or None
        try:
            tag_id = str(uuid.UUID(row.get("description_tag_id", "")))
        except ValueError:
            outcome.errors.append(f"Redak {line_no}: description_tag_id nije valjan.")
            continue
        if status is None:
            outcome.errors.append(f"Redak {line_no}: decision mora biti da ili ne.")
        elif not 2 <= len(reviewer) <= 40:
            outcome.errors.append(f"Redak {line_no}: upiši inicijale u reviewer (2-40 znakova).")
        elif _AUTOMATED.search(reviewer):
            outcome.errors.append(
                f"Redak {line_no}: reviewer mora biti osoba iz tima, ne AI ({reviewer})."
            )
        elif note is not None and len(note) > 500:
            outcome.errors.append(f"Redak {line_no}: review_note je dulji od 500 znakova.")
        else:
            decisions.append((tag_id, status, reviewer, note))
    if outcome.errors:
        return outcome
    now = datetime.now(UTC)
    with engine.begin() as conn:
        for tag_id, status, reviewer, note in decisions:
            changed = conn.execute(
                text(
                    """
                    UPDATE prostoriq.description_tag
                    SET status = :st, reviewed_at = :at, reviewer = :who, review_note = :note
                    WHERE description_tag_id = CAST(:id AS uuid) AND status = 'pending_review'
                    """
                ),
                {"st": status, "at": now, "who": reviewer, "note": note, "id": tag_id},
            ).rowcount
            if not changed:
                outcome.not_pending += 1
            elif status == "approved":
                outcome.approved += 1
            else:
                outcome.rejected += 1
    return outcome
