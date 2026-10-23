from __future__ import annotations

import re
from typing import Any

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


def _parts(value: str) -> list[str]:
    return [x.strip().lower() for x in re.split(r"[,;/|]+", str(value or "")) if x.strip()]


def _words(value: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[A-Za-z0-9À-ž+.-]{2,}", str(value or ""))]


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
    return terms[:10]


def profile_match(profile: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    hay = " ".join([
        str(profile.get("company_type") or ""),
        str(profile.get("category") or ""),
        str(profile.get("audience") or ""),
        str(profile.get("description") or ""),
        str(profile.get("country") or ""),
        str(profile.get("city") or ""),
    ]).lower()

    earned = 0.0
    possible = 0.0
    matched: list[str] = []
    gaps: list[str] = []
    components: list[dict[str, Any]] = []

    industry_value = str(workspace.get("industry") or "").strip()
    industries = _industry_terms(industry_value)
    if industries:
        possible += 45
        hits = [x for x in industries if x in hay or any(w in hay for w in _words(x) if len(w) >= 3)]
        points = 45 if len(hits) >= 2 else 35 if hits else 0
        earned += points
        if hits:
            matched.append(f"Industry · {industry_value or hits[0]}")
        components.append({"label": "Industry / category", "points": points, "max_points": 45, "reason": ", ".join(hits[:4]) if hits else "No category evidence in the basic profile."})

    regions = _parts(workspace.get("region") or "")
    if regions:
        possible += 25
        hits = [x for x in regions if _region_hit(x, profile)]
        points = 25 if hits else 0
        earned += points
        if hits:
            matched.append(f"Location · {hits[0]}")
        components.append({"label": "Location", "points": points, "max_points": 25, "reason": str(profile.get("country") or "Country not verified")})

    audience = str(workspace.get("audience") or "Any").strip().lower()
    if audience and audience != "any":
        possible += 15
        actual = str(profile.get("audience") or "").lower()
        hit = audience in actual or (audience == "b2b" and "b2b" in actual) or (audience == "b2c" and "b2c" in actual)
        points = 15 if hit else 0
        earned += points
        if hit:
            matched.append(audience.upper())
        components.append({"label": "Business model", "points": points, "max_points": 15, "reason": str(profile.get("audience") or "Not classified")})

    keywords = _parts(workspace.get("keywords") or "")
    if keywords:
        possible += 15
        hits = [x for x in keywords if x in hay or any(w in hay for w in _words(x) if len(w) >= 3)]
        points = min(15, 7 + 4 * len(hits)) if hits else 0
        earned += points
        if hits:
            matched.append("Keywords · " + ", ".join(hits[:2]))
        components.append({"label": "Keywords", "points": points, "max_points": 15, "reason": ", ".join(hits[:4]) if hits else "No keyword match in the basic profile."})

    if str(workspace.get("company_size") or "").strip():
        gaps.append("Company size is not scored until public size evidence is available.")

    score = round(earned / possible * 100) if possible else 50
    label = "Strong profile match" if score >= 70 else "Possible profile match" if score >= 45 else "Low profile match"
    return {
        "score": max(0, min(100, score)),
        "label": label,
        "matched": matched[:4],
        "gaps": gaps,
        "components": components,
    }


def _workspace_decision(profile: dict[str, Any], match: dict[str, Any], workspace_result: dict[str, Any] | None) -> dict[str, Any]:
    source = profile.get("source") or {}
    base = dict(profile.get("decision") or {})
    if str(source.get("status") or "") in {"Needs better source", "Limited"} or base.get("decision") == "SOURCE NEEDED":
        return {
            "decision": "SOURCE NEEDED", "fit": None, "timing": None,
            "confidence": 25, "priority": None,
            "reason": source.get("reason") or "A stronger corporate source is needed before this workspace can score the account.",
        }
    if workspace_result:
        return {
            "decision": str(workspace_result.get("decision") or "REVIEW"),
            "fit": workspace_result.get("fit"),
            "timing": workspace_result.get("timing"),
            "confidence": workspace_result.get("confidence"),
            "priority": workspace_result.get("priority"),
            "reason": str(workspace_result.get("reason") or "Workspace-specific analysis complete."),
        }
    if profile.get("data_level") == "Researched":
        return {
            "decision": "RESEARCH", "fit": None, "timing": None, "confidence": None, "priority": None,
            "reason": "Company facts already exist, but this workspace-specific fit and outreach layer has not been generated yet.",
        }
    return {
        "decision": "RESEARCH", "fit": None, "timing": None, "confidence": None, "priority": None,
        "reason": "Select and research this company before making a sales decision.",
    }


def discover_for_workspace(workspace_id: str, q: str = "", limit: int = 60, page: int = 1) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    icp = get_icp()
    selected = set(int(x) for x in workspace.get("selected_ids") or [])
    items: list[dict[str, Any]] = []
    for row in search_universe(workspace, q=q, scan_limit=1800):
        profile = basic_company_profile(row, icp)
        match = profile_match(profile, workspace)
        profile["profile_match"] = match
        profile["selected"] = int(profile.get("id") or 0) in selected
        profile["universe_source"] = str(row.get("seed_source") or row.get("data_origin") or "public data")
        # Keep manually selected accounts visible; otherwise suppress clearly weak basic matches.
        if profile["selected"] or int(match.get("score") or 0) >= 35:
            items.append(profile)
    items.sort(key=lambda x: (
        -int((x.get("profile_match") or {}).get("score") or 0),
        -int(x.get("completeness") or 0),
        str(x.get("company") or "").lower(),
    ))
    total = len(items)
    limit = max(10, min(int(limit), 120))
    page = max(1, int(page))
    start = (page - 1) * limit
    return {
        "workspace": {k: v for k, v in workspace.items() if k != "company_results"},
        "items": items[start:start + limit],
        "total_candidates": total,
        "page": page,
        "page_size": limit,
        "pages": max(1, (total + limit - 1) // limit),
    }


def selected_profiles(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    icp = get_icp()
    rows: list[dict[str, Any]] = []
    for cid in workspace.get("selected_ids") or []:
        row = get_company(int(cid))
        if not row:
            continue
        profile = full_company_profile(row, icp)
        match = profile_match(profile, workspace)
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
    rows.sort(key=lambda x: (
        0 if x.get("workspace_intelligence") else 1,
        -int(((x.get("decision") or {}).get("priority") or 0)),
        -int((x.get("profile_match") or {}).get("score") or 0),
    ))
    return rows


def workspace_detail(workspace_id: str) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    selected = selected_profiles(workspace)
    waiting = [x for x in selected if (x.get("decision") or {}).get("decision") in {"RESEARCH", "SOURCE NEEDED"}]
    researched = [x for x in selected if bool(x.get("workspace_intelligence")) and (x.get("decision") or {}).get("decision") != "SOURCE NEEDED"]
    recommended = [x for x in researched if (x.get("decision") or {}).get("decision") == "CONTACT"]
    monitor = [x for x in researched if (x.get("decision") or {}).get("decision") == "MONITOR"]
    skipped = [x for x in researched if (x.get("decision") or {}).get("decision") == "SKIP"]
    review = [x for x in researched if (x.get("decision") or {}).get("decision") not in {"CONTACT", "MONITOR", "SKIP"}]
    public_workspace = {k: v for k, v in workspace.items() if k != "company_results"}
    return {
        "workspace": public_workspace,
        "counts": {
            "selected": len(selected),
            "researched": len(researched),
            "waiting": len(waiting),
            "recommended": len(recommended),
            "monitor": len(monitor),
            "skip": len(skipped),
        },
        "selected": selected,
        "waiting": waiting,
        "researched": researched,
        "recommended": recommended,
        "monitor": monitor,
        "skip": skipped,
        "review": review,
    }


def workspace_company_context(workspace_id: str, company_id: int) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    row = get_company(company_id)
    if not workspace or not row or int(company_id) not in {int(x) for x in workspace.get("selected_ids") or []}:
        return None
    icp = get_icp()
    profile = full_company_profile(row, icp)
    match = profile_match(profile, workspace)
    result = get_workspace_result(workspace_id, company_id)
    return {
        "workspace": {k: v for k, v in workspace.items() if k not in {"company_results", "selected_ids"}},
        "company_id": company_id,
        "profile_match": match,
        "intelligence": result or {},
        "decision": _workspace_decision(profile, match, result),
    }


def workspace_index() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for workspace in list_workspaces():
        detail = workspace_detail(workspace["id"])
        counts = (detail or {}).get("counts") or {}
        public_workspace = {k: v for k, v in workspace.items() if k != "company_results"}
        out.append({**public_workspace, "counts": counts})
    return out
