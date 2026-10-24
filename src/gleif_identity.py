from __future__ import annotations

from typing import Any

import requests

GLEIF_BASE = "https://api.gleif.org/api/v1"
USER_AGENT = "LeadScope/7.3 (public legal entity identity resolution; https://github.com/breddpit228-stack/LeadScope)"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _entity_name(entity: dict[str, Any]) -> str:
    legal = entity.get("legalName") or {}
    if isinstance(legal, dict):
        return _text(legal.get("name"))
    return _text(legal)


def lookup_legal_entities(name: str, country: str = "", limit: int = 5, timeout: int = 9) -> dict[str, Any]:
    """Best-effort legal-entity lookup using GLEIF's public LEI API.

    This layer is intentionally identity-only. It does not classify GTM fit and it does
    not turn every LEI record into a Discover prospect.
    """
    query = _text(name)
    if not query:
        return {"status": "not_found", "query": "", "items": [], "total": 0}
    params: dict[str, Any] = {
        "filter[entity.legalName]": query,
        "page[size]": max(1, min(int(limit), 10)),
        "page[number]": 1,
    }
    response = requests.get(
        f"{GLEIF_BASE}/lei-records",
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.api+json, application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json() if response.content else {}
    data = payload.get("data") or [] if isinstance(payload, dict) else []
    items: list[dict[str, Any]] = []
    requested_country = _text(country).lower()
    for item in data:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") or {}
        entity = attrs.get("entity") or {}
        registration = attrs.get("registration") or {}
        legal_address = entity.get("legalAddress") or {}
        hq_address = entity.get("headquartersAddress") or {}
        item_country = _text(legal_address.get("country") or hq_address.get("country"))
        if requested_country and item_country and requested_country not in item_country.lower():
            country_match = False
        else:
            country_match = True
        legal_form = entity.get("legalForm") or {}
        items.append({
            "lei": _text(item.get("id") or attrs.get("lei")),
            "legal_name": _entity_name(entity),
            "jurisdiction": _text(entity.get("jurisdiction")),
            "country": item_country,
            "entity_status": _text(entity.get("status")),
            "category": _text(entity.get("category")),
            "legal_form_code": _text(legal_form.get("id") or legal_form.get("code")) if isinstance(legal_form, dict) else _text(legal_form),
            "registered_as": _text(entity.get("registeredAs")),
            "registration_status": _text(registration.get("status")),
            "initial_registration_date": _text(registration.get("initialRegistrationDate")),
            "last_update_date": _text(registration.get("lastUpdateDate")),
            "country_match": country_match,
            "gleif_url": f"https://search.gleif.org/#/record/{_text(item.get('id') or attrs.get('lei'))}" if _text(item.get("id") or attrs.get("lei")) else "",
        })
    items.sort(key=lambda x: (0 if x.get("country_match") else 1, 0 if str(x.get("entity_status") or "").upper() == "ACTIVE" else 1))
    meta = payload.get("meta") or {} if isinstance(payload, dict) else {}
    pagination = meta.get("pagination") or {} if isinstance(meta, dict) else {}
    try:
        total = int(pagination.get("total") or len(items))
    except Exception:
        total = len(items)
    return {
        "status": "resolved" if items else "not_found",
        "query": query,
        "country": country,
        "total": total,
        "items": items[:max(1, min(int(limit), 10))],
        "source": "GLEIF Global LEI Index",
        "note": "Legal-entity identity evidence only. LeadScope does not treat an LEI record as a sales prospect by itself.",
    }
