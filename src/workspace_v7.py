from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from .company_universe import CATEGORY_ALIASES, search_universe
from .data_engine import company_profile as basic_company_profile
from .data_engine_ext import company_profile as full_company_profile
from .storage import get_company, get_icp
from .workspace_projects import get_workspace, get_workspace_result, list_workspaces

EUROPE_COUNTRIES = {
    "albania", "andorra", "austria", "belarus", "belgium", "bosnia and herzegovina", "bulgaria",
    "croatia", "cyprus", "czech republic", "czechia", "denmark", "estonia", "finland", "france",
    "germany", "greece", "hungary", "iceland", "ireland", "italy", "kosovo", "latvia",
    "liechtenstein", "lithuania", "luxembourg", "malta", "moldova", "monaco", "montenegro",
    "netherlands", "north macedonia", "norway", "poland", "portugal", "romania", "san marino",
    "serbia", "slovakia", "slovenia", "spain", "sweden", "switzerland", "ukraine",
    "united kingdom", "uk", "vatican city",
}

SERVICE_PROVIDER_MARKERS = (
    "software development house", "software development company", "software development partner",
    "technology consulting", "technology consultancy", "consulting company", "consulting firm",
    "consultancy", "agency", "development partner", "delivery partner", "outsourcing",
    "nearshore", "custom software", "bespoke software", "digital transformation services",
    "product studio", "design studio", "engineering services", "software services",
)

CATEGORY_CORE_PHRASES: dict[str, tuple[str, ...]] = {
    "fintech": (
        "fintech", "payment platform", "payments platform", "payment gateway", "digital banking",
        "banking platform", "accounting software", "accounting platform", "payroll software",
        "payroll platform", "lending platform", "credit platform", "spend management",
        "expense management", "financial wellbeing", "financial wellness", "insurtech",
    ),
    "software & saas": ("saas", "software platform", "cloud software", "cloud platform", "api platform", "subscription software"),
    "b2b saas": ("b2b saas", "saas", "software platform", "cloud software", "api platform"),
    "ai & data": ("ai platform", "artificial intelligence", "machine learning", "data platform", "analytics platform", "llm"),
    "cybersecurity": ("cybersecurity", "security platform", "identity security", "fraud prevention", "threat detection", "security software"),
    "marketing & adtech": ("marketing platform", "martech", "adtech", "advertising platform", "attribution platform", "campaign platform"),
    "sales & revops": ("sales platform", "revops", "crm", "sales automation", "prospecting platform", "revenue intelligence"),
    "hr & recruiting": ("hr platform", "recruiting platform", "recruitment platform", "workforce platform", "talent platform", "hr software"),
    "e-commerce & retail": ("e-commerce platform", "ecommerce platform", "retail platform", "commerce platform", "online retail"),
    "marketplaces": ("marketplace", "buyers and sellers", "two-sided platform"),
    "logistics & supply chain": ("logistics platform", "supply chain platform", "freight platform", "fleet platform", "warehouse software"),
    "climate & energy": ("climate tech", "energy platform", "renewable energy", "carbon platform", "sustainability platform"),
    "health & life sciences": ("healthtech", "health platform", "medical platform", "clinical platform", "biotech", "life sciences"),
    "professional services": ("consulting", "consultancy", "agency", "advisory", "professional services", "development house"),
    "manufacturing": ("manufacturing", "industrial platform", "factory software", "production platform"),
    "real estate & proptech": ("proptech", "real estate platform", "property platform", "housing platform"),
    "education & edtech": ("edtech", "education platform", "learning platform", "training platform", "school"),
    "telecom": ("telecom", "telecommunications", "connectivity platform", "network platform"),
    "travel & hospitality": ("travel platform", "hospitality platform", "booking platform", "hotel platform", "tourism platform"),
}


def _parts(value: str) -> list[str]:
    return [x.strip().lower() for x in re.split(r"[,;/|]+", str(value or "")) if x.strip()]


def _words(value: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[A-Za-z0-9À-ž+.-]{2,}", str(value or ""))]


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _domain(value: str) -> str:
    try:
        host = (urlparse(str(value or "")).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _region_hit(region: str, profile: dict[str, Any]) -> bool:
    region = region.strip().lower()
    country = str(profile.get("country") or "").strip().lower()
    city = str(profile.get("city") or "").strip().lower()
    location = f"{country} {city}".strip()
    if region in {"europe", "eu", "european union"}:
        return country in EUROPE_COUNTRIES
    return region in location or any(w in location for w in _words(region) if len(w) >= 3)


def _industry_terms(value: str) -> list[str]:
    key = str(value or "").strip().lower()
    terms = list(CATEGORY_ALIASES.get(key) or [])
    if key and key not in terms:
        terms.insert(0, key)
    return list(dict.fromkeys(x.strip().lower() for x in terms if str(x).strip()))[:12]


def _range(value: str) -> tuple[int, int] | None:
    text = str(value or "").replace("–", "-").replace("—", "-")
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", text)]
    if not nums:
        return None
    if "+" in text:
        return nums[0], 10**9
    if len(nums) == 1:
        return nums[0], nums[0]
    return min(nums[0], nums[1]), max(nums[0], nums[1])


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return max(a[0], b[0]) <= min(a[1], b[1])


def _service_provider(text: str) -> bool:
    hay = str(text or "").lower()
    return any(marker in hay for marker in SERVICE_PROVIDER_MARKERS)


def _structured_text(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    tags = " ".join(str(x) for x in _json_list(row.get("seed_tags_json")))
    return " ".join([
        str(row.get("segment") or ""),
        str(row.get("business_type") or ""),
        tags,
    ]).lower()


def _industry_relationship(profile: dict[str, Any], workspace: dict[str, Any], row: dict[str, Any] | None = None) -> dict[str, Any]:
    industry_value = str(workspace.get("industry") or "").strip()
    key = industry_value.lower()
    terms = _industry_terms(industry_value)
    if not terms:
        return {"kind": "none", "label": "No industry target", "points": 0, "evidence": [], "service_provider": False}

    description = str(profile.get("description") or "").lower()
    identity_text = description[:420]
    structured = _structured_text(row)
    service = _service_provider(description)
    core_terms = list(CATEGORY_CORE_PHRASES.get(key) or tuple(terms[:5]))

    structured_hits = list(dict.fromkeys(x for x in terms if x and x in structured))
    core_hits = list(dict.fromkeys(x for x in core_terms if x and x in identity_text))
    broad_hits = list(dict.fromkeys(x for x in terms if x and x in description))

    if service and key not in {"professional services", "consulting"}:
        if structured_hits or core_hits or broad_hits:
            return {
                "kind": "serves", "label": f"Serves {industry_value} clients", "points": 8,
                "evidence": (core_hits + structured_hits + broad_hits)[:4], "service_provider": True,
            }
        return {"kind": "none", "label": "No primary-industry evidence", "points": 0, "evidence": [], "service_provider": True}

    if key in {"professional services", "consulting"} and service:
        return {"kind": "primary", "label": f"Primary industry · {industry_value}", "points": 40, "evidence": ["service-provider identity"], "service_provider": True}
    if structured_hits and core_hits:
        return {"kind": "primary", "label": f"Primary industry · {industry_value}", "points": 40, "evidence": (structured_hits + core_hits)[:4], "service_provider": False}
    if structured_hits:
        return {"kind": "primary", "label": f"Primary industry · {industry_value}", "points": 36, "evidence": structured_hits[:4], "service_provider": False}
    if len(core_hits) >= 2:
        return {"kind": "primary", "label": f"Primary industry · {industry_value}", "points": 34, "evidence": core_hits[:4], "service_provider": False}
    if len(core_hits) == 1:
        return {"kind": "primary", "label": f"Likely primary industry · {industry_value}", "points": 30, "evidence": core_hits[:4], "service_provider": False}
    if len(broad_hits) >= 2:
        return {"kind": "adjacent", "label": f"Adjacent to {industry_value}", "points": 20, "evidence": broad_hits[:4], "service_provider": False}
    if len(broad_hits) == 1:
        return {"kind": "adjacent", "label": f"Weak {industry_value} signal", "points": 10, "evidence": broad_hits[:4], "service_provider": False}
    return {"kind": "none", "label": "No convincing industry evidence", "points": 0, "evidence": [], "service_provider": False}


def _prepare_profile(profile: dict[str, Any], row: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    profile["team_size_public"] = str(row.get("team_size_public") or "").strip()
    relation = _industry_relationship(profile, workspace, row)
    profile["industry_relationship"] = relation
    if relation.get("kind") == "serves" and relation.get("service_provider"):
        profile["company_type"] = "Professional services"
        profile["category"] = str(row.get("business_type") or row.get("segment") or "Professional services")
    return profile


def profile_match(profile: dict[str, Any], workspace: dict[str, Any], row: dict[str, Any] | None = None) -> dict[str, Any]:
    description_hay = " ".join([
        str(profile.get("description") or ""), str(profile.get("company_type") or ""),
        str(profile.get("category") or ""), str(profile.get("audience") or ""),
    ]).lower()
    earned = 0.0
    possible = 0.0
    matched: list[str] = []
    gaps: list[str] = []
    components: list[dict[str, Any]] = []

    industry_value = str(workspace.get("industry") or "").strip()
    relation = _industry_relationship(profile, workspace, row) if industry_value else {"kind": "none", "label": "No industry target", "points": 0, "evidence": [], "service_provider": False}
    industry_points = 0
    if industry_value:
        possible += 40
        industry_points = int(relation.get("points") or 0)
        earned += industry_points
        if industry_points:
            matched.append(str(relation.get("label") or f"Industry · {industry_value}"))
        if relation.get("kind") == "serves":
            gaps.append(f"The company serves {industry_value} clients but is not clearly a {industry_value} company itself.")
        components.append({"label": "Industry / category", "points": industry_points, "max_points": 40, "reason": str(relation.get("label") or "No convincing industry evidence") + ((" · " + ", ".join(str(x) for x in relation.get("evidence") or [])) if relation.get("evidence") else "")})

    regions = _parts(workspace.get("region") or "")
    if regions:
        possible += 20
        region_hits = [x for x in regions if _region_hit(x, profile)]
        points = 20 if region_hits else 0
        earned += points
        if region_hits:
            matched.append(f"Location · {region_hits[0]}")
        else:
            gaps.append("Location is outside the selected region or is not verified.")
        components.append({"label": "Location", "points": points, "max_points": 20, "reason": str(profile.get("country") or "Country not verified")})

    audience = str(workspace.get("audience") or "Any").strip().lower()
    if audience and audience != "any":
        possible += 15
        actual = str(profile.get("audience") or "").strip().lower()
        if actual == audience:
            points = 15
        elif audience in {"b2b", "b2c"} and actual == "mixed b2b/b2c":
            points = 8
        else:
            points = 0
        earned += points
        if points:
            matched.append(audience.upper() if points == 15 else f"Partial {audience.upper()}")
        elif not actual or actual == "unknown":
            gaps.append("Business model is not verified.")
        components.append({"label": "Business model", "points": points, "max_points": 15, "reason": str(profile.get("audience") or "Not classified")})

    size_target = str(workspace.get("company_size") or "").strip()
    if size_target:
        possible += 15
        wanted = _range(size_target)
        actual_text = str(profile.get("team_size_public") or "").strip()
        actual = _range(actual_text)
        if wanted and actual and _ranges_overlap(wanted, actual):
            overlap = min(wanted[1], actual[1]) - max(wanted[0], actual[0]) + 1
            wanted_span = max(1, wanted[1] - wanted[0] + 1)
            overlap_ratio = min(1.0, overlap / wanted_span)
            points = 15 if overlap_ratio >= 0.7 else 12 if overlap_ratio >= 0.35 else 8
        else:
            points = 0
        earned += points
        if points:
            matched.append(f"Size · {actual_text}")
        elif not actual:
            gaps.append("Company size is unknown, so no size-match points were awarded.")
        else:
            gaps.append(f"Verified company size ({actual_text}) does not match {size_target}.")
        components.append({"label": "Company size", "points": points, "max_points": 15, "reason": actual_text or "No public team-size evidence."})

    keywords = _parts(workspace.get("keywords") or "")
    if keywords:
        possible += 10
        hits: list[str] = []
        for keyword in keywords:
            if keyword in description_hay:
                hits.append(keyword)
                continue
            words = [w for w in _words(keyword) if len(w) >= 4]
            if words and all(w in description_hay for w in words):
                hits.append(keyword)
        hits = list(dict.fromkeys(hits))
        points = 10 if len(hits) >= 3 else 8 if len(hits) == 2 else 4 if len(hits) == 1 else 0
        earned += points
        if hits:
            matched.append("Keywords · " + ", ".join(hits[:2]))
        components.append({"label": "Keywords", "points": points, "max_points": 10, "reason": ", ".join(hits[:4]) if hits else "No specific workspace keyword is supported by the basic profile."})

    score = max(0, min(100, round(earned / possible * 100) if possible else 50))
    if score >= 88:
        label = "Excellent profile match"
    elif score >= 74:
        label = "Strong profile match"
    elif score >= 60:
        label = "Good profile match"
    elif score >= 42:
        label = "Possible profile match"
    else:
        label = "Low profile match"
    best_match = relation.get("kind") == "primary" and industry_points >= 30 and score >= 55 if industry_value else score >= 60
    return {"score": score, "label": label, "matched": matched[:5], "gaps": gaps[:5], "components": components, "tier": "best" if best_match else "broader", "industry_points": industry_points, "industry_relation": relation}


def _decision_reason(decision: str, fit: Any, timing: Any, confidence: Any) -> str:
    f = int(fit or 0) if fit is not None else None
    t = int(timing or 0) if timing is not None else None
    c = int(confidence or 0) if confidence is not None else None
    if decision == "CONTACT":
        return f"Strong workspace fit ({f}/100) and timely signals ({t}/100) make this account worth contacting now."
    if decision == "MONITOR":
        return f"Workspace fit is solid ({f}/100), but timing is still weak ({t}/100); keep this account on watch."
    if decision == "POTENTIAL":
        if t is not None and t >= 60 and f is not None and f < 60:
            return f"Recent activity is strong ({t}/100), but workspace fit is only moderate ({f}/100); this is promising, not top priority."
        if f is not None and f >= 50:
            return f"The account has moderate workspace fit ({f}/100), but one or more criteria are still below recommendation level."
        return "Some evidence is promising, but the account is not strong enough yet for a recommendation."
    if decision == "SKIP":
        return f"Research confidence is sufficient ({c}/100), but workspace fit is too weak ({f}/100) to justify outreach."
    return "The available evidence needs further review before deciding what to do."


def _workspace_decision(profile: dict[str, Any], match: dict[str, Any], workspace_result: dict[str, Any] | None) -> dict[str, Any]:
    source = profile.get("source") or {}
    base = dict(profile.get("decision") or {})
    if str(source.get("status") or "") in {"Needs better source", "Limited"} or base.get("decision") == "SOURCE NEEDED":
        return {"decision": "SOURCE NEEDED", "fit": None, "timing": None, "confidence": 25, "priority": None, "reason": source.get("reason") or "A stronger corporate source is needed before this workspace can score the account."}
    if workspace_result:
        decision = str(workspace_result.get("decision") or "POTENTIAL").upper()
        if decision == "REVIEW":
            decision = "POTENTIAL"
        fit = workspace_result.get("fit")
        timing = workspace_result.get("timing")
        confidence = workspace_result.get("confidence")
        reason = str(workspace_result.get("reason") or "").strip()
        if not reason or "combines this workspace" in reason.lower():
            reason = _decision_reason(decision, fit, timing, confidence)
        return {"decision": decision, "fit": fit, "timing": timing, "confidence": confidence, "priority": workspace_result.get("priority"), "reason": reason}
    if profile.get("data_level") == "Researched":
        return {"decision": "RESEARCH", "fit": None, "timing": None, "confidence": None, "priority": None, "reason": "Company facts already exist, but this workspace-specific fit and outreach layer has not been generated yet."}
    return {"decision": "RESEARCH", "fit": None, "timing": None, "confidence": None, "priority": None, "reason": "Shortlist and research this company before making a sales decision."}


def discover_for_workspace(workspace_id: str, q: str = "", limit: int = 60, page: int = 1) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    icp = get_icp()
    selected = {int(x) for x in workspace.get("selected_ids") or []}
    best: list[dict[str, Any]] = []
    broader: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    seen_names: set[str] = set()

    for row in search_universe(workspace, q=q, scan_limit=2200):
        profile = _prepare_profile(basic_company_profile(row, icp), row, workspace)
        domain = _domain(str(profile.get("website") or ""))
        name_key = str(profile.get("company") or "").strip().lower()
        if domain and domain in seen_domains:
            continue
        if not domain and name_key and name_key in seen_names:
            continue
        if domain:
            seen_domains.add(domain)
        if name_key:
            seen_names.add(name_key)

        match = profile_match(profile, workspace, row)
        profile["profile_match"] = match
        profile["selected"] = int(profile.get("id") or 0) in selected
        profile["universe_source"] = str(row.get("seed_source") or row.get("data_origin") or "public data")
        profile["match_tier"] = str(match.get("tier") or "broader")
        profile["industry_relationship"] = match.get("industry_relation") or {}
        score = int(match.get("score") or 0)
        if profile["match_tier"] == "best":
            best.append(profile)
        elif score >= 28 or profile["selected"]:
            broader.append(profile)

    def sorter(item: dict[str, Any]):
        match = item.get("profile_match") or {}
        relation = match.get("industry_relation") or {}
        relation_rank = {"primary": 0, "adjacent": 1, "serves": 2, "none": 3}.get(str(relation.get("kind") or "none"), 3)
        return (relation_rank, -int(match.get("score") or 0), -int(match.get("industry_points") or 0), -int(item.get("completeness") or 0), str(item.get("company") or "").lower())

    best.sort(key=sorter)
    broader.sort(key=sorter)
    total = len(best)
    limit = max(10, min(int(limit), 120))
    page = max(1, int(page))
    start = (page - 1) * limit
    relation_counts = {"primary": 0, "adjacent": 0, "serves": 0, "none": 0}
    for item in best + broader:
        kind = str(((item.get("profile_match") or {}).get("industry_relation") or {}).get("kind") or "none")
        relation_counts[kind if kind in relation_counts else "none"] += 1
    return {"workspace": {k: v for k, v in workspace.items() if k != "company_results"}, "items": best[start:start + limit], "broader_items": broader[:16] if page == 1 else [], "total_candidates": total, "broader_candidates": len(broader), "relation_counts": relation_counts, "page": page, "page_size": limit, "pages": max(1, (total + limit - 1) // limit)}


def selected_profiles(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    icp = get_icp()
    rows: list[dict[str, Any]] = []
    for cid in workspace.get("selected_ids") or []:
        row = get_company(int(cid))
        if not row:
            continue
        profile = _prepare_profile(full_company_profile(row, icp), row, workspace)
        match = profile_match(profile, workspace, row)
        workspace_result = get_workspace_result(str(workspace.get("id") or ""), int(cid))
        profile["profile_match"] = match
        profile["workspace_intelligence"] = workspace_result or {}
        profile["research_decision"] = dict(profile.get("decision") or {})
        profile["decision"] = _workspace_decision(profile, match, workspace_result)
        if workspace_result:
            profile["workspace_fit_summary"] = str(workspace_result.get("fit_summary") or "")
            profile["workspace_personalized_opener"] = str(workspace_result.get("personalized_opener") or "")
            profile["workspace_email_draft"] = str(workspace_result.get("email_draft") or "")
        rows.append(profile)
    rows.sort(key=lambda x: (0 if x.get("workspace_intelligence") else 1, -int(((x.get("decision") or {}).get("priority") or 0)), -int((x.get("profile_match") or {}).get("score") or 0)))
    return rows


def workspace_detail(workspace_id: str) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    selected = selected_profiles(workspace)
    waiting = [x for x in selected if (x.get("decision") or {}).get("decision") in {"RESEARCH", "SOURCE NEEDED"}]
    ready = [x for x in waiting if (x.get("decision") or {}).get("decision") == "RESEARCH"]
    source_issues = [x for x in waiting if (x.get("decision") or {}).get("decision") == "SOURCE NEEDED"]
    researched = [x for x in selected if bool(x.get("workspace_intelligence")) and (x.get("decision") or {}).get("decision") != "SOURCE NEEDED"]
    recommended = [x for x in researched if (x.get("decision") or {}).get("decision") == "CONTACT"]
    monitor = [x for x in researched if (x.get("decision") or {}).get("decision") == "MONITOR"]
    potential = [x for x in researched if (x.get("decision") or {}).get("decision") in {"POTENTIAL", "REVIEW"}]
    skipped = [x for x in researched if (x.get("decision") or {}).get("decision") == "SKIP"]
    public_workspace = {k: v for k, v in workspace.items() if k != "company_results"}
    return {"workspace": public_workspace, "counts": {"selected": len(selected), "researched": len(researched), "waiting": len(waiting), "ready": len(ready), "source_issues": len(source_issues), "recommended": len(recommended), "monitor": len(monitor), "potential": len(potential), "skip": len(skipped)}, "selected": selected, "waiting": waiting, "ready": ready, "source_issues": source_issues, "researched": researched, "recommended": recommended, "monitor": monitor, "potential": potential, "review": potential, "skip": skipped}


def workspace_company_context(workspace_id: str, company_id: int) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    row = get_company(company_id)
    if not workspace or not row or int(company_id) not in {int(x) for x in workspace.get("selected_ids") or []}:
        return None
    icp = get_icp()
    profile = _prepare_profile(full_company_profile(row, icp), row, workspace)
    match = profile_match(profile, workspace, row)
    result = get_workspace_result(workspace_id, company_id)
    return {"workspace": {k: v for k, v in workspace.items() if k not in {"company_results", "selected_ids"}}, "company_id": company_id, "profile_match": match, "intelligence": result or {}, "decision": _workspace_decision(profile, match, result)}


def workspace_index() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for workspace in list_workspaces():
        detail = workspace_detail(workspace["id"])
        counts = (detail or {}).get("counts") or {}
        public_workspace = {k: v for k, v in workspace.items() if k != "company_results"}
        out.append({**public_workspace, "counts": counts})
    return out
