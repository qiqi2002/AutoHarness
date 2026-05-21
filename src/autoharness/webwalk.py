"""Restricted web walking primitives for demo and integration tasks."""

from __future__ import annotations

import html
import re
import ssl
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from autoharness.errors import AutoHarnessError, ErrorCode


@dataclass(frozen=True)
class WebWalkLimits:
    max_pages: int = 12
    max_depth: int = 5
    timeout_seconds: int = 30
    request_delay_ms: int = 1000
    max_text_chars: int = 12000


@dataclass(frozen=True)
class WebLink:
    id: int
    text: str
    url: str


@dataclass
class WebPage:
    url: str
    title: str
    text: str
    links: list[WebLink]
    html: str = field(repr=False)


class WebWalkTool:
    """Small HTTP-only browser with domain and page-count restrictions."""

    def __init__(
        self,
        *,
        allowed_domains: Iterable[str],
        limits: WebWalkLimits | None = None,
        user_agent: str = "AutoHarness-WebWalk/0.1",
    ) -> None:
        self.allowed_domains = tuple(domain.lower() for domain in allowed_domains)
        self.limits = limits or WebWalkLimits()
        self.user_agent = user_agent
        self.pages: list[WebPage] = []
        self._last_request_at = 0.0

    def open(self, url: str) -> WebPage:
        self._ensure_allowed(url)
        if len(self.pages) >= self.limits.max_pages:
            raise AutoHarnessError(
                ErrorCode.ACTION_NOT_ALLOWED,
                f"webwalk page limit exceeded: {self.limits.max_pages}",
            )
        self._respect_delay()

        request = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=self.limits.timeout_seconds, context=_ssl_context()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read()
        page_html = raw.decode(charset, errors="replace")
        page = parse_page(url, page_html, max_text_chars=self.limits.max_text_chars)
        self.pages.append(page)
        self._last_request_at = time.monotonic()
        return page

    def current_page(self) -> WebPage | None:
        if not self.pages:
            return None
        return self.pages[-1]

    def open_link(self, link_id: int) -> WebPage:
        page = self.current_page()
        if page is None:
            raise AutoHarnessError(ErrorCode.ACTION_NOT_ALLOWED, "no current page")
        if link_id < 0 or link_id >= len(page.links):
            raise AutoHarnessError(ErrorCode.ACTION_NOT_ALLOWED, f"link id out of range: {link_id}")
        return self.open(page.links[link_id].url)

    def trace(self) -> list[dict[str, str | int]]:
        return [
            {
                "step": index,
                "url": page.url,
                "title": page.title,
                "links": len(page.links),
            }
            for index, page in enumerate(self.pages, start=1)
        ]

    def _ensure_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            raise AutoHarnessError(ErrorCode.ACTION_NOT_ALLOWED, f"unsupported URL scheme: {parsed.scheme}")
        if not any(host == domain or host.endswith(f".{domain}") for domain in self.allowed_domains):
            raise AutoHarnessError(ErrorCode.ACTION_NOT_ALLOWED, f"domain not allowed: {host}")

    def _respect_delay(self) -> None:
        if not self.pages or self.limits.request_delay_ms <= 0:
            return
        elapsed_ms = (time.monotonic() - self._last_request_at) * 1000
        remaining_ms = self.limits.request_delay_ms - elapsed_ms
        if remaining_ms > 0:
            time.sleep(remaining_ms / 1000)


def parse_page(url: str, page_html: str, *, max_text_chars: int = 12000) -> WebPage:
    parser = _PageParser(url)
    parser.feed(page_html)
    text = _normalize_text(" ".join(parser.text_parts))
    return WebPage(
        url=url,
        title=_normalize_text(parser.title),
        text=text[:max_text_chars],
        links=parser.links,
        html=page_html,
    )


class _PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.text_parts: list[str] = []
        self.links: list[WebLink] = []
        self._in_title = False
        self._skip_depth = 0
        self._current_href: str | None = None
        self._current_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = attr.get("href")
            if href:
                self._current_href = urljoin(self.base_url, href)
                self._current_link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._current_href:
            text = _normalize_text(" ".join(self._current_link_text))
            if text:
                self.links.append(WebLink(id=len(self.links), text=text, url=self._current_href))
            self._current_href = None
            self._current_link_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = html.unescape(data).strip()
        if not value:
            return
        if self._in_title:
            self.title += f" {value}"
        elif self._current_href:
            self._current_link_text.append(value)
        self.text_parts.append(value)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ModuleNotFoundError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())
