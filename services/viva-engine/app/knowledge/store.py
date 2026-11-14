"""The system's own knowledge base: what it learned from reviews, sessions and the web."""

import ipaddress
import socket
import urllib.robotparser
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.knowledge.bm25 import BM25Index
from app.models import KnowledgeItem, KnowledgeSource

USER_AGENT = "AIProjectExaminer-KnowledgeBot/0.1"
CHUNK_WORDS = 180

# Tests replace this with an httpx.MockTransport.
transport: httpx.BaseTransport | None = None
# Tests may disable the private-address guard (MockTransport has no real DNS).
check_public_address = True


class IngestError(Exception):
    pass


def add_item(db: Session, source_type: str, source_ref: str, text: str, title=None) -> None:
    db.add(KnowledgeItem(source_type=source_type, source_ref=source_ref, title=title, text=text))


# Knowledge that belongs to particular students: searchable by staff, never put in a
# prompt or a question for someone else.
PRIVATE_SOURCES = {"project", "reviewed_qa"}


def search(
    db: Session,
    query: str,
    k: int = 5,
    source_types: set[str] | None = None,
    exclude_types: set[str] | None = None,
) -> list:
    query_items = select(KnowledgeItem)
    if source_types:
        query_items = query_items.where(KnowledgeItem.source_type.in_(source_types))
    if exclude_types:
        query_items = query_items.where(KnowledgeItem.source_type.not_in(exclude_types))
    items = {str(item.id): item for item in db.scalars(query_items)}
    if not items:
        return []
    index = BM25Index([(item_id, item.text) for item_id, item in items.items()])
    return [(items[item_id], score) for item_id, score in index.search(query, k)]


# -- web ingestion ---------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg"}
    _BLOCKS = {"p", "li", "pre", "h1", "h2", "h3", "h4", "td", "dd", "blockquote", "code"}

    def __init__(self) -> None:
        super().__init__()
        self.depth_skip = 0
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self.depth_skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self.depth_skip:
            self.depth_skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.depth_skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return parser.title.strip(), "\n".join(line for line in lines if line)


def chunk(text: str, size: int = CHUNK_WORDS) -> list[str]:
    words = text.split()
    return [
        " ".join(words[i : i + size]) for i in range(0, len(words), size) if words[i : i + size]
    ]


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise IngestError("Only https:// URLs are accepted")
    allowed = get_settings().knowledge_allowed_domains
    host = parsed.hostname.lower()
    if allowed and not any(host == d or host.endswith("." + d) for d in allowed):
        raise IngestError(f"{host} is not in the allowed knowledge domains")
    if check_public_address:
        # Never let a faculty-supplied URL reach internal services (SSRF).
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(host, 443)}
        except socket.gaierror as exc:
            raise IngestError(f"Cannot resolve {host}") from exc
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise IngestError(f"{host} resolves to a non-public address")


def _robots_allow(client: httpx.Client, url: str) -> bool:
    robots_url = urljoin(url, "/robots.txt")
    try:
        response = client.get(robots_url)
    except httpx.HTTPError:
        return True  # no robots.txt reachable: allowed by convention
    if response.status_code >= 400:
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def ingest_url(db: Session, source: KnowledgeSource) -> None:
    """Fetch one page, split it into chunks and index them. Records success or the error."""
    settings = get_settings()
    try:
        _validate_url(source.url)
        with httpx.Client(
            timeout=20,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,  # a redirect could point at an internal host
        ) as client:
            if not _robots_allow(client, source.url):
                raise IngestError("robots.txt does not allow fetching this page")
            response = client.get(source.url)
            if response.status_code != 200:
                raise IngestError(f"HTTP {response.status_code}")
            if len(response.content) > settings.knowledge_max_page_kb * 1024:
                raise IngestError("Page is too large")
            content_type = response.headers.get("content-type", "")
            if "html" in content_type:
                title, text = html_to_text(response.text)
            elif content_type.startswith("text/"):
                title, text = source.url, response.text
            else:
                raise IngestError(f"Unsupported content type {content_type or 'unknown'}")
        pieces = chunk(text)
        if not pieces:
            raise IngestError("No readable text on the page")
        db.execute(delete(KnowledgeItem).where(KnowledgeItem.source_ref == source.url))
        for piece in pieces:
            add_item(db, "web", source.url, piece, title=title or source.url)
        source.status, source.error, source.items = "indexed", None, len(pieces)
    except (IngestError, httpx.HTTPError) as exc:
        source.status, source.error, source.items = "failed", str(exc), 0
    source.fetched_at = datetime.now(UTC)
    db.commit()
