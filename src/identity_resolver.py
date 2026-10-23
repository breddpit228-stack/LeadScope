from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "LeadScope/6.3 (public company identity resolution; https://github.com/breddpit228-stack/LeadScope)"

# A few high-confidence corporate-source hints for domains that are intentionally
# product/storefront surfaces rather than useful company-research sources.
CORPORATE_SOURCE_HINTS = {
    "amazon.com": [("Amazon corporate", "https://www.aboutamazon.com")],
    "facebook.com": [("Meta corporate", "https://about.meta.com")],
    "instagram.com": [("Meta corporate", "https://about.meta.com")],
    "whatsapp.com": [("Meta corporate", "https://about.meta.com")],
}


def _host(value: str) -> str:
    try:
        host = (urlparse(value or "").hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _api(params: dict[str, Any], timeout: int = 18) -> dict[str, Any]:
    base = {
        "format": "json",
        "origin": "*",
    }
    base.update(params)
    response = requests.get(
        WIKIDATA_API,
        params=base,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    value = response.json()
    return value if isinstance(value, dict) else {}


def _search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    data = _api({
        "action": "wbsearchentities",
        "search": query,
        "language": "en",
        "uselang": "en",
        "type": "item",
        "limit": max(1, min(limit, 10)),
    })
    return [x for x in data.get("search", []) if isinstance(x, dict)]


def _entities(ids: list[str]) -> dict[str, Any]:
    clean = [x for x in ids if re.fullmatch(r"Q\d+", str(x or ""))]
    if not clean:
        return {}
    data = _api({
        "action": "wbgetentities",
        "ids": "|".join(clean[:50]),
        "languages": "en",
        "props": "labels|descriptions|claims",
    })
    entities = data.get("entities") or {}
    return entities if isinstance(entities, dict) else {}


def _claim_values(entity: dict[str, Any], prop: str) -> list[Any]:
    claims = (entity.get("claims") or {}).get(prop) or []
    out: list[Any] = []
    for claim in claims:
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
            out.append(value)
        except Exception:
            continue
    return out


def _urls(entity: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for value in _claim_values(entity, "P856"):
        text = str(value or "").strip()
        if text.startswith(("http://", "https://")) and text not in out:
            out.append(text)
    return out


def _entity_ids(entity: dict[str, Any], prop: str) -> list[str]:
    out: list[str] = []
    for value in _claim_values(entity, prop):
        if isinstance(value, dict):
            qid = str(value.get("id") or "")
            if re.fullmatch(r"Q\d+", qid) and qid not in out:
                out.append(qid)
    return out


def _label(entity: dict[str, Any], fallback: str = "") -> str:
    try:
        return str(entity.get("labels", {}).get("en", {}).get("value") or fallback)
    except Exception:
        return fallback


def _description(entity: dict[str, Any]) -> str:
    try:
        return str(entity.get("descriptions", {}).get("en", {}).get("value") or "")
    except Exception:
        return ""


def resolve_company_identity(company_name: str, website: str = "") -> dict[str, Any]:
    submitted_host = _host(website)
    search_term = str(company_name or "").strip() or submitted_host.split(".")[0]
    results = _search(search_term, limit=7)
    qids = [str(x.get("id") or "") for x in results if x.get("id")]
    entities = _entities(qids)

    ranked: list[dict[str, Any]] = []
    query_norm = _norm(search_term)
    query_tokens = set(query_norm.split())
    for result in results:
        qid = str(result.get("id") or "")
        entity = entities.get(qid) or {}
        label = _label(entity, str(result.get("label") or ""))
        description = _description(entity) or str(result.get("description") or "")
        websites = _urls(entity)
        score = 0
        label_norm = _norm(label)
        if label_norm == query_norm:
            score += 55
        overlap = len(query_tokens & set(label_norm.split()))
        score += min(25, overlap * 10)
        if submitted_host and any(_host(x) == submitted_host for x in websites):
            score += 35
        if any(term in description.lower() for term in ["company", "business", "software", "technology", "platform", "corporation"]):
            score += 8
        ranked.append({
            "wikidata_id": qid,
            "name": label,
            "description": description,
            "official_websites": websites,
            "parent_ids": _entity_ids(entity, "P749"),
            "score": min(100, score),
            "wikidata_url": f"https://www.wikidata.org/wiki/{qid}" if qid else "",
        })

    ranked.sort(key=lambda x: -int(x.get("score") or 0))
    parent_ids: list[str] = []
    for item in ranked[:4]:
        for qid in item.get("parent_ids") or []:
            if qid not in parent_ids:
                parent_ids.append(qid)
    parents = _entities(parent_ids)

    source_candidates: list[dict[str, Any]] = []
    seen_hosts: set[str] = set()

    def add_source(name: str, url: str, kind: str, confidence: str, qid: str = "") -> None:
        host = _host(url)
        if not host or host in seen_hosts:
            return
        seen_hosts.add(host)
        source_candidates.append({
            "name": name,
            "url": url,
            "host": host,
            "kind": kind,
            "confidence": confidence,
            "wikidata_id": qid,
        })

    for hint_name, hint_url in CORPORATE_SOURCE_HINTS.get(submitted_host, []):
        add_source(hint_name, hint_url, "known corporate source", "High")

    for item in ranked[:4]:
        confidence = "High" if int(item.get("score") or 0) >= 70 else "Medium" if int(item.get("score") or 0) >= 45 else "Low"
        for url in item.get("official_websites") or []:
            if _host(url) != submitted_host:
                add_source(str(item.get("name") or "Company"), url, "official website", confidence, str(item.get("wikidata_id") or ""))
        for parent_id in item.get("parent_ids") or []:
            parent = parents.get(parent_id) or {}
            parent_name = _label(parent, parent_id)
            for url in _urls(parent):
                if _host(url) != submitted_host:
                    add_source(parent_name, url, "parent company website", "Medium", parent_id)

    best = ranked[0] if ranked else None
    return {
        "query": search_term,
        "submitted_website": website,
        "submitted_domain": submitted_host,
        "best_identity": best,
        "identity_candidates": ranked[:5],
        "source_candidates": source_candidates[:8],
        "status": "resolved" if best else "not_found",
        "note": "Candidates are suggestions from public identity data. LeadScope does not replace the submitted company or source automatically.",
    }
