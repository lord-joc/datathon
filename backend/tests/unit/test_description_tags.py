"""Rules for tags from the D01 "Opis strukture" field, on phrases from the real 2024 list."""

import pytest

from app.ai.tags import TAG_LABELS, rule_tags
from app.pipeline.description_tags import import_review, rules_sha256


def _tags(text: str) -> dict[str, int | None]:
    return {p.tag: p.value for p in rule_tags(text)}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "jedne prostorije i sanitarnog čvora u prizemlju ulične zgrade",
            {"room_count": 1, "toilet": None, "ground_floor": None, "street_facing": None},
        ),
        ("tri prostorije u podrumu ulične zgrade", {"room_count": 3, "basement": None, "street_facing": None}),
        (
            "jedne prostorije u prizemlju površine 61,78 m2 i dvije prostorije u podrumu "
            "površine 29,43 m2, oznake B11-L4, u roh-bau izvedbi",
            {"room_count": 3, "ground_floor": None, "basement": None, "unfinished": None},
        ),
        ("lokala broj 12-podhodnik-Siget", {"underpass": None}),
        ("ulaz sa platoa, ulazni prostor, četri prostorije i sanitarni čvor", {"room_count": 4, "toilet": None}),
        ("jedne prostorije u razizemlju zgrade, oznake br. 7", {"room_count": 1, "ground_floor": None}),
        ("ateliera na mansardi zgrade", {"attic": None}),
        ("dvije prostorije i WC-a u prizemlju ulične zgrade", {"room_count": 2, "toilet": None, "ground_floor": None, "street_facing": None}),
        ("prostor u objektu 6 - baraka; oznake A-11", {"barrack": None}),
        ("prostorije u prizemlju ulične zgrade (derutno)", {"ground_floor": None, "street_facing": None, "poor_condition": None}),
        ("uredske prostorije", {}),
        ("", {}),
    ],
)  # fmt: skip
def test_rules_on_real_phrases(text: str, expected: dict[str, int | None]) -> None:
    assert _tags(text) == expected


def test_evidence_is_the_words_from_the_text() -> None:
    found = {
        p.tag: p for p in rule_tags("dvije prostorije u podrumu, te jedne prostorije u podrumu")
    }
    assert found["basement"].evidence == "podrumu"
    assert found["room_count"].evidence == "dvije prostorije; jedne prostorije"
    assert all(p.method == "rule" for p in found.values())


def test_words_inside_other_words_do_not_match() -> None:
    # "kat" must not match inside "kategorija", "izba" not inside "izbor".
    assert _tags("izbor kategorija") == {}


def test_every_tag_has_a_croatian_label_and_rules_have_a_stable_hash() -> None:
    assert all(TAG_LABELS.values())
    assert rules_sha256() == rules_sha256()
    assert len(rules_sha256()) == 64


@pytest.mark.parametrize("reviewer", ["claude-chat", "ChatGPT", "AI", "bot tima"])
def test_a_model_cannot_be_the_reviewer(reviewer: str) -> None:
    body = (
        "description_tag_id;decision;reviewer\n"
        f"ca52ff38-3666-4f4d-a47c-de9d5e60c6ea;da;{reviewer}\n"
    )
    # Validation fails before any database access, so no engine is needed.
    outcome = import_review(None, body.encode())  # type: ignore[arg-type]
    assert outcome.errors and "osoba iz tima" in outcome.errors[0]
