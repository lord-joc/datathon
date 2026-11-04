"""D20 lease parsing, D09 notice parsing, brief rules and topic proposals (ADR24)."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from app.adapters.lease_csv import parse_lease_csv
from app.adapters.notices_html import clean_text, fetch_notices, parse_article, parse_list
from app.adapters.registry import load_registry
from app.ai import brief, news
from app.api.v1.market import rent_stats
from app.gis.district_names import mentioned_districts

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
DISTRICTS = [
    ("00116", "Donji grad"),
    ("00108", "Donja Dubrava"),
    ("00132", "Gornja Dubrava"),
    ("00680", "Trnje"),
    ("00663", "Trešnjevka - jug"),
    ("00671", "Trešnjevka - sjever"),
    ("00426", "Novi Zagreb - istok"),
    ("00434", "Novi Zagreb - zapad"),
]


def _spec(code: str) -> Any:
    return load_registry(CONFIG_DIR).get(code)


LEASE_HEADER = (
    "Ugovori;;;;;;;;\n"
    "ID;Vrsta ugovora;Zakupnk/Korisnik;Adresa;Predmet ugovora;"
    '"Datum\npotpisa/ovjere\nugovora";"Zakupnina/\nNaknada mjesečno\n";Valuta;Status\n'
)


def _lease(rows: str) -> bytes:
    return (LEASE_HEADER + rows).encode("cp1250")


PERSON = "ANA TESTIĆ"
GOOD_ROW = (
    f"7;Ugovor o zakupu poslovnog prostora;{PERSON};ZAGREB,  MARTIĆEVA 0014;"
    f"ID 5003, Ugovor o zakupu poslovnog prostora, {PERSON}, MARTIĆEVA 0014, 100,00 m2, "
    "djelatnost ugostiteljska usluživanja pića;08.01.2024.;1.250,50;EUR;Aktivan ugovor\n"
)


def test_lease_keeps_only_allowlisted_fields_and_never_a_name() -> None:
    parsed = parse_lease_csv(_lease(GOOD_ROW), _spec("D20"))
    assert not parsed.blocking
    record = parsed.records[0]
    assert record["space_id"] == "5003"
    assert record["address"] == "MARTIĆEVA 0014"
    assert record["area_m2"] == "100.00"
    assert record["monthly_rent_eur"] == "1250.50"
    assert record["signed_date"] == "2024-01-08"
    assert record["activity"] == "ugostiteljska usluživanja pića"
    assert PERSON not in repr(record) and "TESTIĆ" not in repr(record)


def test_lease_skips_free_use_contracts_and_stops_on_changed_header() -> None:
    free = (
        "8;Ugovor o uporabi i korištenju;VRTIĆ;ZAGREB,  ILICA 0001;ID 1, 50,00 m2, djelatnost x;"
        "02.01.2024.;0,00;EUR;Aktivan ugovor\n"
    )
    parsed = parse_lease_csv(_lease(GOOD_ROW + free), _spec("D20"))
    assert [r["contract_key"] for r in parsed.records] == ["7"]
    broken = parse_lease_csv(b"Neko;Drugo;Zaglavlje\n1;2;3\n", _spec("D20"))
    assert broken.first_blocking_code == "schema_changed"


def test_lease_row_without_area_or_activity_is_a_warning_not_a_guess() -> None:
    row = (
        "9;Ugovor o zakupu poslovnog prostora;X;ZAGREB,  ILICA 0001;ID 1, bez podataka;"
        "02.01.2024.;100,00;EUR;Aktivan ugovor\n"
    )
    parsed = parse_lease_csv(_lease(GOOD_ROW + row), _spec("D20"))
    assert len(parsed.records) == 1
    assert [i.code for i in parsed.issues] == ["lease_incomplete"]


LIST_HTML = """
<div class="listaitem"><div class="datum"><i></i>27.10.2026.</div>
<h4><a href="/utakmica-dinamo/227211">Utakmica</a></h4><hr></div>
<div class="listaitem"><h4><a href="https://example.org/tudi/123">Tuđi članak</a></h4></div>
<div class="listaitem"><h4><a href="/gradonacelnik">Nije članak</a></h4></div>
<div><h4><a href="/izvan-liste/999">Izvan popisa</a></h4></div>
"""
ARTICLE_HTML = """
<div id="clanak_container"><h1>Slavonska avenija 1c</h1>
<div class="datum">27.10.2026.</div>
<div id="opis">Regulacija prometa.<br>Od 3. 11. 2026.<script>alert(1)</script>
<img src="x"><form>polje</form></div></div><div id="drugo">Navigacija</div>
"""


def test_list_follows_only_articles_on_the_same_host() -> None:
    items = parse_list(LIST_HTML, "https://www.zagreb.hr/privremene-regulacije-prometa/1880")
    assert [i.url for i in items] == ["https://www.zagreb.hr/utakmica-dinamo/227211"]
    assert items[0].published_date == "2026-10-27"


def test_city_news_layout_is_a_link_around_the_title() -> None:
    html = """
    <a href="/skola-precko/227429"><img src="x"><hr/><div class="naslov">Škola</div></a>
    <a href="/sve-vijesti/17"><span>Bez naslova</span></a>
    <div class="naslov">Naslov bez poveznice</div>
    """
    items = parse_list(html, "https://www.zagreb.hr/gradske-vijesti/17")
    assert [i.url for i in items] == ["https://www.zagreb.hr/skola-precko/227429"]
    assert items[0].published_date is None


def test_article_is_plain_text_without_scripts_or_navigation() -> None:
    article = parse_article(ARTICLE_HTML)
    assert article.title == "Slavonska avenija 1c"
    assert article.published == "27.10.2026"
    body = clean_text(article.body)
    assert body == "Regulacija prometa.\nOd 3. 11. 2026."


class _Fetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, *, max_bytes: int) -> SimpleNamespace:
        self.calls.append(url)
        return SimpleNamespace(content=self.pages[url].encode())


def test_fetch_waits_between_requests_and_stops_without_a_recognised_list() -> None:
    spec = _spec("D09")
    list_url = "https://www.zagreb.hr/privremene-regulacije-prometa/1880"
    news_url = "https://www.zagreb.hr/gradske-vijesti/17"
    fetcher = _Fetcher(
        {
            list_url: LIST_HTML,
            news_url: "<p>Drugačiji raspored</p>",
            "https://www.zagreb.hr/utakmica-dinamo/227211": ARTICLE_HTML,
        }
    )
    waits: list[float] = []
    content = fetch_notices(spec, fetcher, sleep=waits.append)  # type: ignore[arg-type]
    assert b"utakmica-dinamo" in content
    assert waits == [5.0, 5.0]
    from app.adapters.http import FetchError

    empty = _Fetcher({list_url: "<p/>", news_url: "<p/>"})
    with pytest.raises(FetchError) as exc:
        fetch_notices(spec, empty, sleep=waits.append)  # type: ignore[arg-type]
    assert exc.value.code == "schema_changed"


def test_brief_reads_area_budget_and_priorities_with_the_users_words() -> None:
    facts = brief.read_brief(
        "Mali kafić oko 45 m2 za studente blizu tramvaja, parking mi nije bitan, do 1.200 eura."
    )
    assert facts.area_m2 == 45
    assert facts.budget_eur == 1200
    by_criterion = {p.criterion: p for p in facts.priorities}
    assert by_criterion["universities"].level == 3
    assert by_criterion["universities"].evidence == "studente"
    assert by_criterion["transit"].level == 3
    assert by_criterion["parking"].level == 0


@pytest.mark.parametrize(
    ("text", "criterion", "level"),
    [
        ("Treba mi izlog i puno prolaznika", "street", 3),
        ("Bez parkinga, klijenti dolaze pješice", "parking", 0),
        ("Igraonica za djecu blizu škole", "schools", 3),
        ("Ne treba mi javni prijevoz", "transit", 0),
    ],
)
def test_brief_priority_rules(text: str, criterion: str, level: int) -> None:
    found = {p.criterion: p.level for p in brief.extract_priorities(text)}
    assert found[criterion] == level  # type: ignore[index]


def test_brief_invents_nothing_from_a_plain_description() -> None:
    facts = brief.read_brief("Radionica za popravak bicikala")
    assert facts == brief.BriefFacts(None, None, [])


def test_activity_matching_for_rent_statistics() -> None:
    assert brief.activity_matches("cafe", "ugostiteljske djelatnosti usluživanja pića")
    assert brief.activity_matches("personal_care", "njege lica, depilacije lica i tijela")
    assert not brief.activity_matches("cafe", "popravak računala")
    assert not brief.activity_matches("unknown", "bilo što")


def test_rent_median_needs_enough_contracts() -> None:
    assert rent_stats([1.0, 2.0], 5).median_eur_per_m2 is None
    assert rent_stats([1.0, 2.0], 5).contracts == 2
    full = rent_stats([1.0, 2.0, 3.0, 4.0, 5.0], 5)
    assert (full.p25_eur_per_m2, full.median_eur_per_m2, full.p75_eur_per_m2) == (2.0, 3.0, 4.0)


def test_districts_in_inflected_text_and_zagreb_alone_names_none() -> None:
    assert mentioned_districts("Otvaram u Gradu Zagrebu", DISTRICTS) == []
    assert [d for d, _ in mentioned_districts("nešto u Trnju", DISTRICTS)] == ["00680"]
    assert [d for d, _ in mentioned_districts("na Trešnjevci", DISTRICTS)] == ["00663", "00671"]
    assert [d for d, _ in mentioned_districts("u Donjoj Dubravi", DISTRICTS)] == ["00108"]
    assert [d for d, _ in mentioned_districts("u Novom Zagrebu", DISTRICTS)] == ["00426", "00434"]
    assert [d for d, _ in mentioned_districts("u donjem gradu", DISTRICTS)] == ["00116"]


class _Embedder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]:
        rows = [np.array(self.vectors[t], dtype=np.float32) for t in texts]
        return np.stack([r / np.linalg.norm(r) for r in rows])


TOPICS = {"traffic_works": "promet", "events": "dogadjaj", "irrelevant": "nista"}
VECTORS = {
    "promet": [1.0, 0.0, 0.0],
    "dogadjaj": [0.0, 1.0, 0.0],
    "nista": [0.0, 0.0, 1.0],
    "naslov": [1.0, 0.1, 0.0],
    "nejasno": [1.0, 0.95, 0.0],
    "cestitka": [0.0, 0.0, 1.0],
}


@pytest.mark.parametrize(
    ("title", "status", "topic"),
    [
        ("naslov", "classified", "traffic_works"),
        ("nejasno", "uncertain", None),
        ("cestitka", "irrelevant", "irrelevant"),
    ],
)
def test_topic_needs_similarity_and_a_margin(title: str, status: str, topic: str | None) -> None:
    result = news.classify(title, [], _Embedder(VECTORS), TOPICS, 0.45, 0.05)
    assert (result.status, result.topic) == (status, topic)


def test_dates_only_when_complete_and_end_is_exclusive() -> None:
    text = "Radovi od 3. 11. 2026. do 21. studenoga 2026. Sastanak 5. 12. bez godine."
    dates = news.extract_dates(text)
    assert dates == [date(2026, 11, 3), date(2026, 11, 21)]
    window = news.validity_window(dates, date(2026, 10, 27))
    assert window is not None
    assert window[0].isoformat() == "2026-11-02T23:00:00+00:00"
    assert window[1].isoformat() == "2026-11-21T23:00:00+00:00"
    assert news.validity_window([date(2020, 1, 1)], date(2026, 10, 27)) is None


def test_street_found_in_case_forms_and_short_names_ignored() -> None:
    streets = ["Slavonska avenija", "Ilica", "Vlaška ulica", "Ulica"]
    assert news.mentioned_streets("Radovi na Slavonskoj aveniji", streets) == ["Slavonska avenija"]
    assert news.mentioned_streets("regulacija u Vlaškoj", streets) == ["Vlaška ulica"]
    # A five-letter name is too easy to hit by accident; a person can still add it in review.
    assert news.mentioned_streets("Ilica je zatvorena", streets) == []


def test_chunks_respect_size_and_overlap() -> None:
    words = " ".join(f"w{i}" for i in range(250))
    offsets = []
    position = 0
    for word in words.split():
        offsets.append((position, position + len(word)))
        position += len(word) + 1

    class _Tok:
        def encode(self, text: str, add_special_tokens: bool = True) -> SimpleNamespace:
            assert add_special_tokens is False
            return SimpleNamespace(offsets=offsets)

    chunks = news.content_chunks(words, _Tok(), 96, 16)
    assert [len(c.split()) for c in chunks] == [96, 96, 90]
    assert chunks[0].split()[-16:] == chunks[1].split()[:16]


def test_summary_states_only_facts() -> None:
    window = news.validity_window([date(2026, 11, 3), date(2026, 11, 21)], None)
    text = news.template_summary("Radovi", "Vlaška ulica", window)
    assert text == (
        "Grad Zagreb objavio je obavijest „Radovi” za lokaciju Vlaška ulica "
        "od 3. 11. 2026. do 21. 11. 2026. Provjerite izvornu obavijest."
    )
