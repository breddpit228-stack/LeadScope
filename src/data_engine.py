from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from .source_quality import MARKETPLACE_OR_STOREFRONT, SOCIAL_OR_LOGIN_HEAVY, assess_source_quality


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _text(*values: Any) -> str:
    chunks: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            chunks.extend(str(x) for x in value)
        else:
            chunks.append(str(value or ""))
    return " ".join(chunks).lower()


def _host(value: str) -> str:
    try:
        host = (urlparse(value or "").hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _signal_value(signal: dict[str, Any]) -> int:
    try:
        return max(0, min(100, int(float(signal.get("signal_value") or 0))))
    except Exception:
        return 0


def _source_profile(row: dict[str, Any]) -> dict[str, Any]:
    website = str(row.get("website") or row.get("source_url") or "")
    host = _host(website)
    pages = _json_list(row.get("source_pages_json"))
    fetch_status = str(row.get("fetch_status") or "").strip().lower()
    researched = bool(str(row.get("quality_status") or "").strip())

    if host in SOCIAL_OR_LOGIN_HEAVY:
        return {"type": "login-heavy / social platform", "confidence": "Low", "status": "Needs better source", "score_allowed": False}
    if host in MARKETPLACE_OR_STOREFRONT:
        return {"type": "storefront / marketplace", "confidence": "Low", "status": "Needs better source", "score_allowed": False}
    if not pages and not researched and fetch_status in {"", "not fetched"}:
        return {"type": "submitted company domain", "confidence": "Unknown", "status": "Not checked", "score_allowed": None}

    assessed = assess_source_quality(row)
    return {
        "type": assessed.get("source_type") or "public source",
        "confidence": assessed.get("confidence") or "Unknown",
        "status": "Usable" if assessed.get("score_allowed") else "Limited",
        "score_allowed": bool(assessed.get("score_allowed")),
        "reason": assessed.get("reason") or "",
    }


def classify_company(row: dict[str, Any]) -> tuple[str, str]:
    services = _json_list(row.get("services_json"))
    customers = _json_list(row.get("target_customers_json"))
    tags = _json_list(row.get("seed_tags_json"))
    hay = _text(
        row.get("segment"), row.get("business_type"), row.get("company_summary"),
        row.get("public_signals"), services, customers, tags,
    )

    type_rules = [
        ("Fintech", ["fintech", "payments", "banking", "accounting", "payroll", "financial software"]),
        ("AI / data software", ["artificial intelligence", "machine learning", " ai ", "data platform", "analytics"]),
        ("SaaS / software", ["saas", "software", "platform", "cloud", "developer tools", "api"]),
        ("Marketplace", ["marketplace", "buyers and sellers", "commerce platform"]),
        ("E-commerce / retail", ["ecommerce", "e-commerce", "retail", "online store", "shopping"]),
        ("Climate / energy", ["climate", "energy", "carbon", "renewable", "solar", "wind"]),
        ("Professional services", ["consulting", "agency", "professional services", "advisory"]),
        ("Healthcare / biotech", ["healthtech", "healthcare", "biotech", "clinical", "medical"]),
    ]
    company_type = "Technology / company"
    padded = f" {hay} "
    for label, needles in type_rules:
        if any(n in padded for n in needles):
            company_type = label
            break

    b2b_terms = ["b2b", "businesses", "companies", "teams", "enterprise", "merchants", "employers", "organizations", "professionals", "accountants", "developers"]
    b2c_terms = ["consumers", "shoppers", "individuals", "households", "personal use", "customers shop", "consumer"]
    b2b = any(x in hay for x in b2b_terms) or bool(customers and _text(customers).find("business") >= 0)
    b2c = any(x in hay for x in b2c_terms)
    audience = "Mixed B2B/B2C" if b2b and b2c else "B2B" if b2b else "B2C" if b2c else "Unknown"
    return company_type, audience


def data_completeness(row: dict[str, Any]) -> tuple[int, list[str]]:
    services = _json_list(row.get("services_json"))
    customers = _json_list(row.get("target_customers_json"))
    markets = _json_list(row.get("markets_json"))
    pages = _json_list(row.get("source_pages_json"))
    proof = _json_list(row.get("proof_points_json"))
    signals = _json_list(row.get("verified_signals_json"))
    hypotheses = _json_list(row.get("hypotheses_json"))
    company_type, audience = classify_company(row)

    score = 0
    gaps: list[str] = []
    checks = [
        (5, bool(row.get("company")), "company name"),
        (5, bool(row.get("website")), "canonical website"),
        (5, bool(row.get("country")), "country"),
        (2, bool(row.get("city")), "city"),
        (8, bool(row.get("segment")) or bool(row.get("business_type")), "industry/category"),
        (7, company_type != "Technology / company" or bool(row.get("business_type")), "company type"),
        (6, audience != "Unknown", "B2B/B2C classification"),
        (12, bool(str(row.get("company_summary") or row.get("public_signals") or "").strip()), "meaningful description"),
        (10, bool(services), "products/services"),
        (8, bool(customers), "target customers"),
        (6, bool(markets), "markets"),
        (8, bool(pages), "source pages"),
        (6, bool(proof), "commercial proof"),
        (6, bool(signals), "verified signals"),
        (3, bool(hypotheses), "opportunity hypothesis"),
        (3, bool(str(row.get("quality_status") or "").strip()), "research quality status"),
    ]
    for points, present, label in checks:
        if present:
            score += points
        else:
            gaps.append(label)
    return min(100, score), gaps


def _prefilter(row: dict[str, Any], icp: dict[str, Any]) -> dict[str, Any]:
    industries = [str(x).lower() for x in (icp.get("industries") or []) if str(x).strip()]
    preferred = [str(x).lower() for x in (icp.get("preferred_signals") or []) if str(x).strip()]
    required = [str(x).lower() for x in (icp.get("required_signals") or []) if str(x).strip()]
    countries = [str(x).lower() for x in (icp.get("countries") or []) if str(x).strip()]
    tags = _json_list(row.get("seed_tags_json"))
    hay = _text(row.get("segment"), row.get("business_type"), row.get("company_summary"), row.get("public_signals"), tags)
    country = str(row.get("country") or "").lower()

    industry_hits = [x for x in industries if x and x in hay]
    preferred_hits = [x for x in preferred if x and x in hay]
    required_hits = [x for x in required if x and x in hay]

    score = 20
    if industries:
        score += min(45, len(industry_hits) * 18)
    else:
        score += 25
    if preferred:
        score += min(20, len(preferred_hits) * 8)
    else:
        score += 10
    if required:
        score += 15 if required_hits else 0
    else:
        score += 10
    if countries:
        score += 10 if any(x in country for x in countries) else -15
    else:
        score += 5
    score = max(0, min(100, score))
    label = "Strong basic match" if score >= 70 else "Possible match" if score >= 45 else "Low basic match"
    return {"score": score, "label": label, "matched": (industry_hits + preferred_hits + required_hits)[:8]}


def _decision(row: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    researched = bool(str(row.get("quality_status") or "").strip())
    if not researched:
        return {"decision": "RESEARCH", "fit": None, "timing": None, "confidence": None, "priority": None,
                "reason": "Full research has not run yet."}
    if source.get("score_allowed") is False:
        return {"decision": "SOURCE NEEDED", "fit": None, "timing": None, "confidence": 25, "priority": None,
                "reason": source.get("reason") or "The source is not strong enough for defensible scoring."}

    fit = max(0, min(100, int(row.get("research_score") or 0)))
    commercial = [x for x in _json_list(row.get("commercial_signals_json")) if isinstance(x, dict)]
    values = sorted((_signal_value(x) for x in commercial), reverse=True)
    meaningful = [x for x in commercial if _signal_value(x) >= 55 and str(x.get("freshness") or "").lower() in {"current", "recent"}]
    if values:
        top = values[0]
        mean_top = sum(values[:3]) / min(3, len(values))
        timing = round(top * 0.68 + mean_top * 0.32)
    else:
        timing = 20
    if len(meaningful) >= 3:
        timing += 10
    elif len(meaningful) >= 2:
        timing += 6
    timing = min(100, timing)

    quality = str(row.get("quality_status") or "").lower()
    source_conf = str(source.get("confidence") or "").lower()
    confidence = 90 if "ready" in quality else 72 if "partial" in quality else 60
    if source_conf == "medium":
        confidence = min(confidence, 75)
    elif source_conf == "low":
        confidence = min(confidence, 40)

    priority = round(fit * 0.55 + timing * 0.35 + confidence * 0.10)
    if fit >= 60 and timing >= 55 and confidence >= 55 and priority >= 60:
        decision = "CONTACT"
    elif fit >= 60 and confidence >= 50:
        decision = "MONITOR"
    elif fit < 45 and confidence >= 50:
        decision = "SKIP"
    else:
        decision = "REVIEW"
    return {"decision": decision, "fit": fit, "timing": timing, "confidence": confidence, "priority": priority,
            "reason": "Decision combines ICP fit, signal timing and research confidence."}


def _convergence(row: dict[str, Any]) -> dict[str, Any]:
    signals = [x for x in _json_list(row.get("commercial_signals_json")) if isinstance(x, dict)]
    eligible = []
    for x in signals:
        freshness = str(x.get("freshness") or "").lower()
        relevance = str(x.get("offer_relevance") or "").lower()
        strength = str(x.get("strength") or "").lower()
        if _signal_value(x) >= 55 and freshness in {"current", "recent"} and relevance in {"high", "medium"} and strength in {"high", "medium"}:
            eligible.append(x)
    types = []
    for x in eligible:
        t = str(x.get("signal_type") or "other").strip()
        if t and t not in types:
            types.append(t)
    if len(eligible) >= 3:
        label = "Strong convergence"
    elif len(eligible) == 2:
        label = "Signal convergence"
    elif len(eligible) == 1:
        label = "Single meaningful signal"
    else:
        label = "No meaningful convergence"
    return {"count": len(eligible), "label": label, "types": types[:5]}


def _research_gaps(row: dict[str, Any], completeness_gaps: list[str]) -> list[str]:
    important = []
    mapping = {
        "products/services": "Products/services are not sufficiently verified.",
        "target customers": "Target customer segments are not sufficiently verified.",
        "markets": "Geographic/market coverage is incomplete.",
        "commercial proof": "No strong commercial proof point is saved.",
        "verified signals": "No verified recent company signal is saved.",
    }
    for gap in completeness_gaps:
        if gap in mapping:
            important.append(mapping[gap])
    if not str(row.get("team_size_public") or "").strip():
        important.append("Public team-size evidence is missing.")
    if not _json_list(row.get("target_roles_json")):
        important.append("Likely buying roles are not verified.")
    return important[:6]


def _reasons_not_to_contact(row: dict[str, Any], decision: dict[str, Any], convergence: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    fit = decision.get("fit")
    timing = decision.get("timing")
    confidence = decision.get("confidence")
    if fit is not None and fit < 60:
        reasons.append(f"ICP fit is only {fit}/100.")
    if timing is not None and timing < 55:
        reasons.append("No sufficiently strong recent timing trigger is visible.")
    if confidence is not None and confidence < 55:
        reasons.append("Research confidence is too low for aggressive outreach.")
    if convergence.get("count", 0) < 2:
        reasons.append("Fewer than two independent strong/recent signals converge on the same account.")
    if not _json_list(row.get("target_roles_json")):
        reasons.append("A relevant buyer role has not been verified yet.")
    return reasons[:5]


def _timeline(row: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for x in _json_list(row.get("commercial_signals_json")):
        if not isinstance(x, dict):
            continue
        date = str(x.get("observed_date") or x.get("date") or "").strip()
        events.append({
            "date": date,
            "type": str(x.get("signal_type") or "Signal"),
            "title": str(x.get("fact") or "").strip(),
            "source_url": str(x.get("source_url") or "").strip(),
            "signal_value": _signal_value(x),
        })
    events.sort(key=lambda x: x.get("date") or "", reverse=True)
    return events[:12]


def company_profile(row: dict[str, Any], icp: dict[str, Any]) -> dict[str, Any]:
    company_type, audience = classify_company(row)
    completeness, gaps = data_completeness(row)
    source = _source_profile(row)
    prefilter = _prefilter(row, icp)
    decision = _decision(row, source)
    convergence = _convergence(row)
    description = str(row.get("company_summary") or row.get("public_signals") or "").strip()
    if bool(str(row.get("quality_status") or "").strip()):
        level = "Researched"
    elif completeness >= 45:
        level = "Enriched"
    else:
        level = "Indexed"
    return {
        "id": row.get("id"),
        "company": row.get("company") or "",
        "canonical_name": row.get("company") or "",
        "website": row.get("website") or "",
        "canonical_domain": _host(str(row.get("website") or "")),
        "country": row.get("country") or "",
        "city": row.get("city") or "",
        "category": row.get("business_type") or row.get("segment") or company_type,
        "company_type": company_type,
        "audience": audience,
        "description": description,
        "data_level": level,
        "completeness": completeness,
        "missing_fields": gaps,
        "source": source,
        "icp_prefilter": prefilter,
        "decision": decision,
        "signal_convergence": convergence,
        "research_gaps": _research_gaps(row, gaps),
        "reasons_not_to_contact": _reasons_not_to_contact(row, decision, convergence),
        "timeline": _timeline(row),
        "buying_roles": [str(x) for x in _json_list(row.get("target_roles_json"))][:8],
        "angles": [str(x.get("title") or "") for x in _json_list(row.get("hypotheses_json")) if isinstance(x, dict) and x.get("title")][:3],
        "last_checked": row.get("verified_on") or row.get("updated_at") or "",
        "quality_status": row.get("quality_status") or "",
        "data_origin": row.get("data_origin") or "",
    }


def summarize_library(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(profiles)
    indexed = sum(1 for x in profiles if x.get("data_level") == "Indexed")
    enriched = sum(1 for x in profiles if x.get("data_level") == "Enriched")
    researched = sum(1 for x in profiles if x.get("data_level") == "Researched")
    source_needed = sum(1 for x in profiles if (x.get("source") or {}).get("status") in {"Needs better source", "Limited"})
    avg = round(sum(int(x.get("completeness") or 0) for x in profiles) / total) if total else 0
    return {"total": total, "indexed": indexed, "enriched": enriched, "researched": researched,
            "source_needed": source_needed, "average_completeness": avg}
