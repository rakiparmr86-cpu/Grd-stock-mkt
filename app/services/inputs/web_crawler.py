"""WebCrawlerConnector — breadth-first, same-site crawl → document library.

Config
------
    {
      "start_urls": ["https://console.grdworld.com/Schedular/Index"],
      "allowed_domains": ["console.grdworld.com"],   # default: domains of start_urls
      "max_depth": 1,            # 0 = only the start pages
      "max_pages": 50,
      "same_domain_only": true,
      "respect_robots": true,
      "delay_seconds": 1.0,
      "timeout": 15,
      "include_patterns": ["/Schedular/"],   # regex, ANY must match to enqueue
      "exclude_patterns": ["\\.pdf$", "/logout"],
      "user_agent": "GrdStkMktCrawler/1.0",
      "doc_type": "web",
      "auth": { ...see app.services.inputs.auth... }
    }

Yields one ``ConnectorResult`` (DOCS, a single :class:`DocItem`) per page.
"""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Iterator
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.logging import get_logger
from app.services.inputs.auth import build_auth
from app.services.inputs.base import ConfigError, ConnectorResult, DocItem, InputConnector

log = get_logger(__name__)

_HTML_CT = ("text/html", "application/xhtml")


def _strip_html(html: str) -> tuple[str, str, list[str]]:
    """Return (title, visible_text, hrefs). Uses BeautifulSoup if available."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        title = (soup.title.string or "").strip() if soup.title else ""
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
        hrefs = [a["href"] for a in soup.find_all("a", href=True)]
        return title, text, hrefs
    except ModuleNotFoundError:  # pragma: no cover - bs4 is a declared dep
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", html))
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
        return (title.group(1).strip() if title else ""), re.sub(r"\s+", " ", text).strip(), hrefs


class WebCrawlerConnector(InputConnector):
    name = "web_crawler"

    def validate(self) -> None:
        if not self._cfg("start_urls"):
            raise ConfigError("web_crawler: 'start_urls' is required (non-empty list)")

    # -----------------------------------------------------------------
    def _client(self) -> httpx.Client:
        ua = self._cfg("user_agent", "GrdStkMktCrawler/1.0")
        client = httpx.Client(
            headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml"},
            timeout=float(self._cfg("timeout", 15)),
            follow_redirects=True,
        )
        build_auth(self._cfg("auth")).prepare(client)
        return client

    def _robots_ok(self, url: str, ua: str, cache: dict[str, RobotFileParser]) -> bool:
        if not self._cfg("respect_robots", True):
            return True
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        rp = cache.get(root)
        if rp is None:
            rp = RobotFileParser()
            rp.set_url(f"{root}/robots.txt")
            try:
                rp.read()
            except Exception:  # pragma: no cover - network/parse issue → allow
                rp = RobotFileParser()
                rp.parse([])
            cache[root] = rp
        return rp.can_fetch(ua, url)

    def fetch(self) -> Iterator[ConnectorResult]:
        starts = list(self._cfg("start_urls"))
        allowed = set(self._cfg("allowed_domains") or [urlparse(u).netloc for u in starts])
        same_domain = bool(self._cfg("same_domain_only", True))
        max_depth = int(self._cfg("max_depth", 1))
        max_pages = int(self._cfg("max_pages", 50))
        delay = float(self._cfg("delay_seconds", 1.0))
        ua = self._cfg("user_agent", "GrdStkMktCrawler/1.0")
        doc_type = self._cfg("doc_type", "web")
        inc = [re.compile(p) for p in self._cfg("include_patterns", []) or []]
        exc = [re.compile(p) for p in self._cfg("exclude_patterns", []) or []]

        seen: set[str] = set()
        queue: deque[tuple[str, int]] = deque((u, 0) for u in starts)
        robots: dict[str, RobotFileParser] = {}
        served = 0

        with self._client() as client:
            while queue and served < max_pages:
                url, depth = queue.popleft()
                url = url.split("#", 1)[0]
                if url in seen:
                    continue
                seen.add(url)

                if same_domain and urlparse(url).netloc not in allowed:
                    continue
                if exc and any(p.search(url) for p in exc):
                    continue
                if not self._robots_ok(url, ua, robots):
                    log.info("robots.txt disallows %s", url)
                    continue

                try:
                    resp = client.get(url)
                except httpx.HTTPError as e:
                    log.warning("crawl GET failed %s: %s", url, e)
                    continue
                if resp.status_code >= 400:
                    log.warning("crawl %s -> HTTP %s", url, resp.status_code)
                    continue
                if not any(ct in resp.headers.get("content-type", "") for ct in _HTML_CT):
                    continue

                title, text, hrefs = _strip_html(resp.text)
                served += 1
                yield ConnectorResult.of_docs(
                    [DocItem(
                        text=text,
                        source_key=url,
                        metadata={"url": url, "title": title or url, "doc_type": doc_type,
                                  "depth": depth, "http_status": resp.status_code},
                    )],
                    url=url, depth=depth,
                )

                if depth < max_depth:
                    for href in hrefs:
                        nxt = urljoin(url, href).split("#", 1)[0]
                        if nxt in seen or not nxt.startswith(("http://", "https://")):
                            continue
                        if same_domain and urlparse(nxt).netloc not in allowed:
                            continue
                        if inc and not any(p.search(nxt) for p in inc):
                            continue
                        queue.append((nxt, depth + 1))

                if delay:
                    time.sleep(delay)

        log.info("crawl finished: %d page(s) from %d start url(s)", served, len(starts))
