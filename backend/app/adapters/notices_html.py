"""D09: the city's own notices from zagreb.hr (ADR24, FZ13).

List pages and article selectors come from the registry and doc. chapter 11. Only article links
on the same host are followed, at most `MAX_DOCUMENTS` per run, one request per 5 seconds. The
terms of zagreb.hr allow reuse of original content with a link to the source, so every card keeps
the link. Text is plain text only: scripts, images and forms never reach the database.

A changed selector or an empty body stops the import instead of storing a partial article.
"""

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.adapters.http import FetchError, SafeFetcher
from app.adapters.parsing import ParseResult
from app.adapters.registry import SourceSpec

MAX_DOCUMENTS = 100
REQUEST_INTERVAL_S = 5.0
LIST_LABELS = ("Privremene regulacije", "Gradske vijesti")
_DATE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")
_ARTICLE_PATH = re.compile(r"^/[a-z0-9-]+/\d{3,8}$")
_SKIPPED = {"script", "style", "iframe", "form", "img", "svg", "noscript"}
_VOID = {
    "br",
    "hr",
    "img",
    "input",
    "meta",
    "link",
    "area",
    "base",
    "col",
    "embed",
    "source",
    "wbr",
}
_BLOCK = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


@dataclass
class ListItem:
    url: str
    published_date: str | None


class _ListParser(HTMLParser):
    """Two layouts: `.listaitem` with `.datum` and a link in `h4` (traffic notices), and a link
    wrapped around `.naslov` (city news, which has no date on the list)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str | None]] = []
        self._depth = 0
        self._in_date = False
        self._in_h4 = False
        self._date: str | None = None
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "a":
            self._href = dict(attrs).get("href")
        elif "naslov" in classes and self._href:
            self.items.append((self._href, None))
        if self._depth:
            if tag not in _VOID:
                self._depth += 1
            if "datum" in classes:
                self._in_date = True
            if tag == "h4":
                self._in_h4 = True
            href = dict(attrs).get("href")
            if tag == "a" and self._in_h4 and href:
                self.items.append((href, self._date))
        elif tag == "div" and "listaitem" in classes:
            self._depth = 1
            self._date = None

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._href = None
        if self._depth and tag not in _VOID:
            self._depth -= 1
            if tag == "h4":
                self._in_h4 = False
            if tag == "div":
                self._in_date = False

    def handle_data(self, data: str) -> None:
        if self._in_date and self._date is None:
            found = _DATE.search(data)
            if found:
                self._date = found.group(0)


@dataclass
class _Article:
    title: str = ""
    published: str | None = None
    body: list[str] = field(default_factory=list)


class _ArticleParser(HTMLParser):
    """`#clanak_container` > `h1`, `.datum` and the text of `#opis` (including `<br>` breaks)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.article = _Article()
        self._container = 0
        self._opis = 0
        self._skip = 0
        self._in_h1 = False
        self._in_date = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag in _SKIPPED and tag not in _VOID:
            self._skip += 1
            return
        if self._opis and tag in _BLOCK:
            self.article.body.append("\n")
        if tag in _VOID:
            return
        if self._container:
            self._container += 1
            if self._opis:
                self._opis += 1
            elif values.get("id") == "opis":
                self._opis = 1
            if tag == "h1" and not self.article.title:
                self._in_h1 = True
            if "datum" in classes and self.article.published is None:
                self._in_date = True
        elif values.get("id") == "clanak_container":
            self._container = 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED and tag not in _VOID:
            self._skip = max(0, self._skip - 1)
            return
        if tag in _VOID or not self._container:
            return
        self._container -= 1
        if self._opis:
            self._opis -= 1
        if tag == "h1":
            self._in_h1 = False
        self._in_date = False

    def handle_data(self, data: str) -> None:
        if self._skip or not self._container:
            return
        if self._in_h1:
            self.article.title += data
        elif self._in_date:
            found = _DATE.search(data)
            if found:
                self.article.published = found.group(0)
        elif self._opis:
            self.article.body.append(data)


def _iso(value: str | None) -> str | None:
    found = _DATE.search(value or "")
    if not found:
        return None
    day, month, year = (int(g) for g in found.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def clean_text(parts: list[str]) -> str:
    lines = (" ".join(line.split()) for line in "".join(parts).splitlines())
    return "\n".join(line for line in lines if line)


def parse_list(html: str, base_url: str) -> list[ListItem]:
    """Links to articles on the list's own host; anything else is ignored, never fetched."""
    parser = _ListParser()
    parser.feed(html)
    host = urlsplit(base_url).hostname
    items: list[ListItem] = []
    seen: set[str] = set()
    for href, published in parser.items:
        url = urljoin(base_url, href).split("#", 1)[0]
        parts = urlsplit(url)
        if parts.hostname != host or not _ARTICLE_PATH.match(parts.path) or url in seen:
            continue
        seen.add(url)
        items.append(ListItem(url, _iso(published)))
    return items


def parse_article(html: str) -> _Article:
    parser = _ArticleParser()
    parser.feed(html)
    return parser.article


def list_urls(spec: SourceSpec) -> list[str]:
    links = {str(x.get("label")): str(x.get("url")) for x in spec.raw.get("links", [])}
    return [links[label] for label in LIST_LABELS if label in links]


def fetch_notices(
    spec: SourceSpec,
    fetcher: SafeFetcher,
    *,
    sleep: Callable[[float], None] = time.sleep,
    max_documents: int = MAX_DOCUMENTS,
) -> bytes:
    """Fetch lists and articles into one canonical JSON file, the raw artefact of this version.

    A list page without recognised items is tolerated only while another list still yields
    articles; with no articles at all the import fails with `schema_changed`.
    """
    items: dict[str, ListItem] = {}
    documents: list[dict[str, Any]] = []
    first = True

    def get(url: str) -> str:
        nonlocal first
        if not first:
            sleep(REQUEST_INTERVAL_S)
        first = False
        return fetcher.get(url, max_bytes=spec.max_response_bytes).content.decode("utf-8")

    for list_url in list_urls(spec):
        for item in parse_list(get(list_url), list_url):
            items.setdefault(item.url, item)
    if not items:
        raise FetchError("schema_changed", "Na stranicama s popisom nema prepoznatih objava.")
    for item in sorted(items.values(), key=lambda x: x.url)[:max_documents]:
        documents.append({"url": item.url, "list_date": item.published_date, "html": get(item.url)})
    return json.dumps(documents, ensure_ascii=False, sort_keys=True).encode("utf-8")


def parse_notices(content: bytes, spec: SourceSpec) -> ParseResult:
    result = ParseResult()
    try:
        documents = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        result.block("schema_changed", "Neispravan paket objava.")
        return result
    for doc in documents:
        url = str(doc["url"])
        article = parse_article(str(doc["html"]))
        title = " ".join(article.title.split())
        body = clean_text(article.body)
        if not title or not body:
            result.warn("selector_changed", "Objava nema prepoznat naslov ili tekst.", url)
            continue
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        result.records.append(
            {
                "url": url,
                "title": title,
                "published_date": _iso(article.published) or doc.get("list_date"),
                "clean_text": body,
                "sha256": sha,
            }
        )
    if not result.records:
        result.block("selector_changed", "Nijedna objava nema prepoznat naslov i tekst.")
    return result
