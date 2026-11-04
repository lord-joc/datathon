"""Notices and market context end to end on PostGIS (ADR24, FZ13-FZ17).

Import -> proposal -> human review -> public card, through the restricted roles. A card is public
only after a person approves it and only while in date; it never changes a score.
"""

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.ai.model import Embedder, load_ai_config
from app.api.v1 import ai as ai_route
from app.api.v1 import public
from app.api.v1.schemas import ProfileSuggestion
from app.pipeline import news
from app.pipeline.importer import Importer
from tests import fixtures as fx
from tests.integration.support import URL, write_file
from tests.integration.test_public_api import client  # noqa: F401
from tests.unit.test_market_news import ARTICLE_HTML, LEASE_HEADER, PERSON

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="MIGRATION_DATABASE_URL not set"),
]
URL_A = "https://www.zagreb.hr/slavonska-avenija-1c/227162"


class _Tokenizer:
    def encode(self, text_: str, add_special_tokens: bool = True) -> SimpleNamespace:
        offsets, position = [], 0
        for word in text_.split():
            start = text_.index(word, position)
            offsets.append((start, start + len(word)))
            position = start + len(word)
        return SimpleNamespace(offsets=offsets)


class _Embedder:
    """Everything looks like traffic works, so a card is always proposed."""

    tokenizer = _Tokenizer()

    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]:
        config = load_ai_config()
        topics = list(config["topics"].values())
        rows = []
        for t in texts:
            if t in topics:
                vector = [0.0, 0.0, 0.0, 0.0]
                vector[topics.index(t)] = 1.0
            else:
                vector = [1.0, 0.0, 0.0, 0.0]
            rows.append(np.array(vector, dtype=np.float32))
        return np.stack(rows)


def _review_rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))


def _to_csv(rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=news.REVIEW_HEADER, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _import(engine: Engine, tmp_path: Path) -> None:
    imp = Importer(engine, fx.registry(), tmp_path / "raw2")
    html = ARTICLE_HTML.replace("Od 3. 11. 2026.", "Od 3. 11. 2099. do 21. 11. 2099.")
    docs = [{"url": URL_A, "list_date": "2026-10-27", "html": html}]
    path = write_file(tmp_path, "d09.json", json.dumps(docs).encode())
    assert imp.run("D09", idempotency_key="n1", local_file=path).status == "succeeded"
    lease = (
        f"7;Ugovor o zakupu poslovnog prostora;{PERSON};ZAGREB,  VLAŠKA 0015;"
        f"ID 5003, Ugovor, {PERSON}, VLAŠKA 0015, 100,00 m2, djelatnost usluživanja pića;"
        "08.01.2024.;1.000,00;EUR;Aktivan ugovor\n"
    )
    path = write_file(tmp_path, "d20.csv", (LEASE_HEADER + lease).encode("cp1250"))
    assert imp.run("D20", idempotency_key="l1", local_file=path).status == "succeeded"


@pytest.fixture
def notices(
    client: TestClient,  # noqa: F811
    imported: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _import(imported, tmp_path)
    monkeypatch.setattr(ai_route, "get_engine", getattr(public, "get_engine"))  # noqa: B009
    yield client


def test_lease_import_stores_no_names(notices: TestClient, imported: Engine) -> None:
    with imported.connect() as conn:
        row = conn.execute(text("SELECT to_jsonb(l) FROM prostoriq.market_lease l")).scalar_one()
    assert row["activity"] == "usluživanja pića"
    assert "TESTIĆ" not in json.dumps(row, ensure_ascii=False)


def test_card_is_public_only_after_a_person_approves_it(
    notices: TestClient, imported: Engine
) -> None:
    config = load_ai_config()
    embedder = cast(Embedder, _Embedder())
    counts = news.classify_notices(imported, embedder, config)
    assert counts["cards"] == 1
    # Same model and configuration: nothing to redo.
    assert news.classify_notices(imported, embedder, config)["revisions"] == 0

    space = notices.get("/api/v1/spaces/4763/context?profile=cafe")
    assert space.status_code == 200
    assert space.json()["items"] == []

    rows = _review_rows(news.review_template_csv(imported))
    assert len(rows) == 1
    assert rows[0]["url"] == URL_A

    district = notices.get("/api/v1/spaces?profile=cafe&page_size=100").json()["items"]
    target = next(s for s in district if s["space_id"] == "4763")["district_id"]
    filled = {
        **rows[0],
        "decision": "da",
        "reviewer": "Claude",
        "location_label": "Slavonska avenija",
        "district_ids": target,
    }
    refused = news.import_review(imported, _to_csv([filled]))
    assert refused.errors and "osoba" in refused.errors[0]
    assert notices.get("/api/v1/spaces/4763/context?profile=cafe").json()["items"] == []

    accepted = news.import_review(imported, _to_csv([{**filled, "reviewer": "LF"}]))
    assert accepted.approved == 1, accepted
    body = notices.get("/api/v1/spaces/4763/context?profile=cafe").json()
    assert body["total"] == 1
    card = body["items"][0]
    assert card["source_url"] == URL_A
    assert card["temporal_label"] == "announced"
    assert body["pending_review"] == 0

    # Reviewed twice: the earlier decision stands.
    assert news.import_review(imported, _to_csv([{**filled, "reviewer": "LF"}])).not_pending == 1

    with imported.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT count(*) FROM prostoriq.audit_event "
                "WHERE entity_type = 'context_card' AND entity_id = :id"
            ),
            {"id": rows[0]["card_id"]},
        ).scalar_one()
    assert audit == 1


def test_expired_card_disappears_even_if_no_job_ran(
    notices: TestClient, imported: Engine, owner: Engine
) -> None:
    news.classify_notices(imported, cast(Embedder, _Embedder()), load_ai_config())
    rows = _review_rows(news.review_template_csv(imported))
    spaces = notices.get("/api/v1/spaces?profile=cafe&page_size=100").json()["items"]
    target = next(s for s in spaces if s["space_id"] == "4763")["district_id"]
    review = {
        **rows[0],
        "decision": "da",
        "reviewer": "LF",
        "location_label": "Slavonska avenija",
        "district_ids": target,
        "valid_from": "",
        "valid_to": "",
    }
    moment = datetime.now(UTC)
    assert news.import_review(imported, _to_csv([review]), now=moment).approved == 1
    assert notices.get("/api/v1/spaces/4763/context?profile=cafe").json()["total"] == 1
    with owner.begin() as conn:
        conn.execute(
            text("UPDATE prostoriq.context_card SET review_due_at = :t"),
            {"t": moment - timedelta(minutes=1)},
        )
    assert notices.get("/api/v1/spaces/4763/context?profile=cafe").json()["total"] == 0


def test_market_summary_counts_and_hides_small_medians(notices: TestClient) -> None:
    body: dict[str, Any] = notices.get("/api/v1/market?profile=cafe").json()
    assert body["competitor_categories"] == ["bar", "cafe", "pub"]
    assert body["city_rent"]["contracts"] == 1
    assert body["city_rent"]["median_eur_per_m2"] is None
    assert body["lease_reference_period"] == "2024"
    assert any("nisu tržišne" in w.lower() for w in body["warnings"])
    assert len(body["districts"]) >= 1


def test_business_brief_needs_the_model_and_proposes_from_words(
    notices: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suggestion = ProfileSuggestion(
        suggested_profile="cafe",
        status="suggested",
        candidates=[],
        min_similarity=0.3,
        min_margin=0.1,
        method="x",
        model_id="m",
        model_revision="r",
        config_sha256="0" * 64,
    )
    monkeypatch.setattr(ai_route, "_suggest", lambda _: suggestion)
    monkeypatch.setattr(ai_route, "shared_embedder", _Embedder)
    response = notices.post(
        "/api/v1/business-brief",
        json={"description": "Kafić oko 45 m2 za studente, parking nije bitan"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["area_m2"] == 45
    levels = {p["criterion"]: p["level"] for p in body["priorities"]}
    assert levels == {"universities": 3, "parking": 0}
