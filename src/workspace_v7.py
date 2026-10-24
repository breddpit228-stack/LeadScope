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


def _industry_component(profile: dict[str, Any], industry_value: str) -> tuple[int, list[str], str]:
    terms = _industry_terms(industry_value)
    if not terms:
        return 0, [], "No category target configured."

    structured = " ".join([
        str(profile.get("company_type") or ""),
        str(profile.get("category") or ""),
    ]).lower()
    description = str(profile.get("description") or "").lower()

    structured_hits = [term for term in terms if term and term in structured]
    description_hits = [term for term in terms if term and term in description]
    # Preserve order while removing aliases that matched the same phrase repeatedly.
    structured_hits = list(dict.fromkeys(structured_hits))
    description_hits = list(dict.fromkeys(description_hits))

    if structured_hits:
        return 40, structured_hits[:4], "Structured company category matches the workspace category."
    if len(description_hits) >= 3:
        return 30, description_hits[:4], "Several category signals appear in the company description."
    if len(description_hits) == 2:
        return 24, description_hits[:4], "Two category signals appear in the company description."
    if len(description_hits) == 1:
        return 12, description_hits[:4], "Only one broad category signal appears in the company description."
    return 0, [], "No convincing category evidence in the basic profile."


def profile_match(profile: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    description_hay = " ".join([
        str(profile.get("description") or ""),
        str(profile.get("company_type") or ""),
        str(profile.get("category") or ""),
        str(profile.get("audience") or ""),
    ]).lower()

    earned = 0.0
    possible = 0.0
    matched: list[str] = []
    gaps: list[str] = []
    components: list[dict[str, Any]] = []

    industry_value = str(workspace.get("industry") or "").strip()
    industry_points = 0
    if industry_value:
        possible += 40
        industry_points, industry_hits, industry_reason = _industry_component(profile, industry_value)
        earned += industry_points
        if industry_points >= 24:
            matched.append(f"Industry · {industry_value}")
        elif industry_points:
            matched.append(f"Industry signal · {industry_value}")
        components.append({
            "label": "Industry / category", "points": industry_points, "max_points": 40,
            "reason": industry_reason + ((" Evidence: " + ", ".join(industry_hits[:4])) if industry_hits else ""),
        })

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
        components.append({
            "label": "Location", "points": points, "max_points": 20,
            "reason": str(profile.get("country") or "Country not verified"),
        })

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
        components.append({
            "label": "Business model", "points": points, "max_points": 15,
            "reason": str(profile.get("audience") or "Not classified"),
        })

    size_target = str(workspace.get("company_size") or "").strip()
    if size_target:
        possible += 15
        wanted = _range(size_target)
        actual_text = str(profile.get("team_size_public") or "").strip()
        actual = _range(actual_text)
        points = 15 if wanted and actual and _ranges_overlap(wanted, actual) else 0
        earned += points
        if points:
            matched.append(f"Size · {actual_text}")
        elif not actual:
            gaps.append("Company size is unknown, so no size-match points were awarded.")
        else:
            gaps.append(f"Verified company size ({actual_text}) does not match {size_target}.")
        components.append({
            "label": "Company size", "points": points, "max_points": 15,
            "reason": actual_text or "No public team-size evidence.",
        })

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
        points = 10 if len(hits) >= 2 else 5 if len(hits) == 1 else 0
        earned += points
        if hits:
            matched.append("Keywords · " + ", ".join(hits[:2]))
        components.append({
            "label": "Keywords", "points": points, "max_points": 10,
            "reason": ", ".join(hits[:4]) if hits else "No specific workspace keyword is supported by the basic profile.",
        })

    score = round(earned / possible * 100) if possible else 50
    if score >= 85:
        label = "Excellent profile match"
    elif score >= 70:
        label = "Strong profile match"
    elif score >= 55:
        label = "Good profile match"
    elif score >= 40:
        label = "Possible profile match"
    else:
        label = "Low profile match"

    # Best-match status requires actual category evidence when a category was configured.
    if industry_value:
        best_match = industry_points >= 24 and score >= 55
    else:
        best_match = score >= 60

    return {
        "score": max(0, min(100, score)),
        "label": label,
        "matched": matched[:5],
        "gaps": gaps[:5],
        "components": components,
        "tier": "best" if best_match else "broader",
        "industry_points": industry_points,
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


def _attach_size(profile: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    profile["team_size_public"] = str(row.get("team_size_public") or "").strip()
    return profile


def discover_for_workspace(workspace_id: str, q: str = "", limit: int = 60, page: int = 1) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    icp = get_icp()
    selected = set(int(x) for x in workspace.get("selected_ids") or [])
    best: list[dict[str, Any]] = []
    broader: list[dict[str, Any]] = []

    for row in search_universe(workspace, q=q, scan_limit=1800):
        profile = _attach_size(basic_company_profile(row, icp), row)
        match = profile_match(profile, workspace)
        profile["profile_match"] = match
        profile["selected"] = int(profile.get("id") or 0) in selected
        profile["universe_source"] = str(row.get("seed_source") or row.get("data_origin") or "public data")
        profile["match_tier"] = match.get("tier") or "broader"
        score = int(match.get("score") or 0)
        if profile["match_tier"] == "best":
            best.append(profile)
        elif score >= 30 or profile["selected"]:
            broader.append(profile)

    sorter = lambda x: (
        -int((x.get("profile_match") or {}).get("score") or 0),
        -int(x.get("completeness") or 0),
        str(x.get("company") or "").lower(),
    )
    best.sort(key=sorter)
    broader.sort(key=sorter)

    total = len(best)
    limit = max(10, min(int(limit), 120))
    page = max(1, int(page))
    start = (page - 1) * limit
    return {
        "workspace": {k: v for k, v in workspace.items() if k != "company_results"},
        "items": best[start:start + limit],
        "broader_items": broader[:12] if page == 1 else [],
        "total_candidates": total,
        "broader_candidates": len(broader),
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
        profile = _attach_size(full_company_profile(row, icp), row)
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
    source_issues = [x for x in waiting if (x.get("decision") or {}).get("decision") == "SOURCE NEEDED"]
    ready = [x for x in waiting if (x.get("decision") or {}).get("decision") == "RESEARCH"]
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
            "ready": len(ready),
            "source_issues": len(source_issues),
            "recommended": len(recommended),
            "monitor": len(monitor),
            "skip": len(skipped),
        },
        "selected": selected,
        "waiting": waiting,
        "ready": ready,
        "source_issues": source_issues,
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
    profile = _attach_size(full_company_profile(row, icp), row)
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
