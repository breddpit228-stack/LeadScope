from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

try:
    import trafilatura
except ImportError:  # pragma: no cover
    trafilatura = None

USER_AGENT = "ValentynLeadResearchStudio/2.0 (portfolio; public B2B research)"
CORE_HINTS = [
    "about", "company", "services", "solutions", "products", "platform", "industries",
    "customers", "clients", "case-studies", "case-study", "work", "portfolio", "ai",
    "automation", "data", "sales", "marketing", "crm", "consulting", "pricing",
]
SIGNAL_HINTS = [
    "careers", "jobs", "hiring", "press", "news", "updates", "announcements",
    "partners", "partnership", "launch", "releases", "case-studies", "success",
]
SKIP_HINTS = [
    "privacy", "cookie", "terms", "legal", "login", "signin", "signup",
    "events", "webinar", "training", "academy", "contact",
]


@dataclass
class Page:
    url: str
    title: str
    text: str
    status: str

    def as_dict(self) -> dict[str, str]:
        return {"url": self.url, "title": self.title, "text": self.text, "status": self.status}


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http/https URLs are supported")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ValueError("Domain could not be resolved") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Private/local network addresses are not allowed")
    return url


def robots_allowed(url: str, session: requests.Session) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = session.get(robots_url, timeout=7)
        if response.status_code == 404:
            return True
        if response.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        # A missing/unreachable robots file should not turn a public portfolio research tool into a false negative.
        return True


def _request_html(url: str, session: requests.Session, timeout: int = 14) -> tuple[str, str, str]:
    current = _validate_public_url(url)
    for _ in range(5):
        if not robots_allowed(current, session):
            return "", current, "skipped: robots.txt disallows"
        response = session.get(current, timeout=timeout, allow_redirects=False)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                return "", current, "error: redirect without location"
            current = _validate_public_url(urljoin(current, location))
            continue
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            return "", current, f"skipped: unsupported content type {content_type[:60]}"
        return response.text, current, f"fetched:{response.status_code}"
    return "", current, "error: too many redirects"


def _title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title:
        return " ".join(soup.title.get_text(" ", strip=True).split())[:220]
    h1 = soup.find("h1")
    return " ".join(h1.get_text(" ", strip=True).split())[:220] if h1 else ""


def extract_public_text(html: str, max_chars: int = 6500) -> str:
    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                include_links=False,
                favor_precision=True,
                deduplicate=True,
            )
            if extracted:
                return " ".join(extracted.split())[:max_chars]
        except Exception:
            pass
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "aside"]):
        tag.decompose()
    bits: list[str] = []
    for node in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) >= 28:
            bits.append(text)
        if sum(len(x) for x in bits) >= max_chars:
            break
    return " ".join(bits)[:max_chars]


def _normalized_internal_links(base_url: str, html: str) -> list[tuple[int, str, str]]:
    base = urlparse(base_url)
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    ranked: list[tuple[int, str, str]] = []
    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(base_url, str(a["href"])))[0]
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != base.netloc:
            continue
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|svg|zip|docx?|xlsx?)$", parsed.path, flags=re.I):
            continue
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/') or '/'}"
        if clean in seen or clean == base_url.rstrip("/"):
            continue
        seen.add(clean)
        label = f"{parsed.path} {' '.join(a.get_text(' ', strip=True).split())}".lower()
        if any(k in label for k in SKIP_HINTS):
            continue
        core_score = sum(6 for k in CORE_HINTS if k in label)
        signal_score = sum(4 for k in SIGNAL_HINTS if k in label)
        depth = max(0, parsed.path.strip("/").count("/"))
        if core_score <= 0 and signal_score <= 0:
            continue
        kind = "signal" if signal_score > core_score else "core"
        score = max(core_score, signal_score) - depth
        ranked.append((score, clean, kind))
    ranked.sort(key=lambda x: (-x[0], 0 if x[2] == "core" else 1, len(x[1])))
    return ranked


def fetch_company_pages(start_url: str, max_pages: int = 6, progress=None) -> tuple[list[dict[str, str]], str]:
    if progress:
        progress("fetching", "Opening company website…", 8)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})

    html, final_url, status = _request_html(start_url, session)
    if progress:
        progress("fetching", "Homepage fetched. Discovering relevant pages…", 18)
    if not html:
        return [], status

    pages: list[Page] = []
    home_text = extract_public_text(html)
    if home_text:
        pages.append(Page(final_url, _title(html), home_text, status))

    candidates = _normalized_internal_links(final_url, html)
    core = [(score, url, kind) for score, url, kind in candidates if kind == "core"]
    signal = [(score, url, kind) for score, url, kind in candidates if kind == "signal"]
    # Reserve up to two pages for observable commercial/timing signals.
    core_budget = max(1, max_pages - 2)
    ordered = core[:core_budget] + signal[:2] + core[core_budget:]
    for _, url, _kind in ordered:
        if len(pages) >= max_pages:
            break
        try:
            page_html, page_url, page_status = _request_html(url, session)
            if not page_html:
                continue
            text = extract_public_text(page_html)
            if len(text) < 180:
                continue
            fingerprint = set(text.lower().split()[:160])
            duplicate = False
            for existing in pages:
                other = set(existing.text.lower().split()[:160])
                if fingerprint and other and len(fingerprint & other) / max(1, min(len(fingerprint), len(other))) > 0.82:
                    duplicate = True
                    break
            if not duplicate:
                pages.append(Page(page_url, _title(page_html), text, page_status))
                if progress:
                    pct = min(42, 18 + len(pages) * 4)
                    progress("fetching", f"Fetched {len(pages)} relevant public page(s)…", pct)
        except Exception:
            continue

    return [p.as_dict() for p in pages], f"fetched {len(pages)} public page(s)"
