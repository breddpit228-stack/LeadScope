from __future__ import annotations

import re
from typing import Any

from .data_engine import company_profile as basic_company_profile
from .data_engine_ext import company_profile as full_company_profile
from .storage import get_company, get_icp, list_companies
from .workspace_projects import get_workspace, list_workspaces

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

    industries = _parts(workspace.get("industry") or "")
    if industries:
        possible += 45
        hits = [x for x in industries if x in hay or any(w in hay for w in _words(x) if len(w) >= 3)]
        if hits:
            earned += 45 if len(hits) >= min(2, len(industries)) else 35
            matched.append(f"Industry · {hits[0]}")

    regions = _parts(workspace.get("region") or "")
    if regions:
        possible += 25
        hits = [x for x in regions if _region_hit(x, profile)]
        if hits:
            earned += 25
            matched.append(f"Location · {hits[0]}")

    audience = str(workspace.get("audience") or "Any").strip().lower()
    if audience and audience != "any":
        possible += 15
        actual = str(profile.get("audience") or "").lower()
        if audience in actual or (audience == "b2b" and "b2b" in actual) or (audience == "b2c" and "b2c" in actual):
            earned += 15
            matched.append(audience.upper())

    keywords = _parts(workspace.get("keywords") or "")
    if keywords:
        possible += 15
        hits = [x for x in keywords if x in hay or any(w in hay for w in _words(x) if len(w) >= 3)]
        if hits:
            earned += min(15, 7 + 4 * len(hits))
            matched.append("Keywords · " + ", ".join(hits[:2]))

    if str(workspace.get("company_size") or "").strip():
        gaps.append("Company size is not scored until public size evidence is available.")

    score = round(earned / possible * 100) if possible else 50
    label = "Strong profile match" if score >= 70 else "Possible profile match" if score >= 45 else "Low profile match"
    return {"score": max(0, min(100, score)), "label": label, "matched": matched[:4], "gaps": gaps}


def _workspace_decision(profile: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    base = dict(profile.get("decision") or {})
    source = profile.get("source") or {}
    if str(source.get("status") or "") in {"Needs better source", "Limited"} or base.get("decision") == "SOURCE NEEDED":
        return {
            "decision": "SOURCE NEEDED", "fit": None, "timing": None,
            "confidence": 25, "priority": None,
            "reason": source.get("reason") or "A stronger corporate source is needed before this workspace can score the account.",
        }
    if profile.get("data_level") != "Researched":
        return {"decision": "RESEARCH", "fit": None, "timing": None, "confidence": None, "priority": None,
                "reason": "Select and research this company before making a sales decision."}

    fit = int(match.get("score") or 0)
    timing = int(base.get("timing") or 20)
    confidence = int(base.get("confidence") or 55)
    priority = round(fit * 0.55 + timing * 0.35 + confidence * 0.10)

    if fit >= 60 and timing >= 55 and confidence >= 55 and priority >= 60:
        decision = "CONTACT"
    elif fit >= 60 and confidence >= 50:
        decision = "MONITOR"
    elif fit < 45 and confidence >= 50:
        decision = "SKIP"
    else:
        decision = "REVIEW"
    return {
        "decision": decision,
        "fit": fit,
        "timing": timing,
        "confidence": confidence,
        "priority": priority,
        "reason": "Workspace decision combines this workspace's profile match with researched timing and evidence confidence.",
    }


def _candidate_rows(workspace: dict[str, Any], q: str = "", scan_limit: int = 900) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}

    queries: list[str] = []
    if q.strip():
        queries.append(q.strip())
    industries = _parts(workspace.get("industry") or "")
    regions = _parts(workspace.get("region") or "")
    keywords = _parts(workspace.get("keywords") or "")
    if industries:
        queries.append(industries[0])
    if keywords:
        queries.append(keywords[0])
    if regions and regions[0] not in {"europe", "eu", "european union"}:
        queries.append(regions[0])

    for query in queries[:3]:
        for row in list_companies(q=query, limit=min(scan_limit, 600), offset=0):
            seen[int(row["id"])] = row

    if len(seen) < 350:
        for row in list_companies(limit=min(scan_limit, 600), offset=0):
            seen[int(row["id"])] = row

    return list(seen.values())[:scan_limit]


def discover_for_workspace(workspace_id: str, q: str = "", limit: int = 120) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    icp = get_icp()
    selected = set(int(x) for x in workspace.get("selected_ids") or [])
    items: list[dict[str, Any]] = []
    for row in _candidate_rows(workspace, q=q):
        profile = basic_company_profile(row, icp)
        match = profile_match(profile, workspace)
        profile["profile_match"] = match
        profile["selected"] = int(profile.get("id") or 0) in selected
        items.append(profile)
    items.sort(key=lambda x: (
        -int((x.get("profile_match") or {}).get("score") or 0),
        -int(x.get("completeness") or 0),
        str(x.get("company") or "").lower(),
    ))
    qualified = [
        x for x in items
        if int((x.get("profile_match") or {}).get("score") or 0) >= 35 or bool(x.get("selected"))
    ]
    if not qualified and items:
        qualified = items[:20]
    return {
        "workspace": workspace,
        "items": qualified[:max(1, min(int(limit), 250))],
        "total_candidates": len(qualified),
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
        profile["profile_match"] = match
        profile["research_decision"] = dict(profile.get("decision") or {})
        profile["decision"] = _workspace_decision(profile, match)
        rows.append(profile)
    rows.sort(key=lambda x: (
        0 if x.get("data_level") == "Researched" else 1,
        -int(((x.get("decision") or {}).get("priority") or 0)),
        -int((x.get("profile_match") or {}).get("score") or 0),
    ))
    return rows


def workspace_detail(workspace_id: str) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    selected = selected_profiles(workspace)
    waiting = [x for x in selected if x.get("data_level") != "Researched" or (x.get("decision") or {}).get("decision") == "SOURCE NEEDED"]
    researched = [x for x in selected if x.get("data_level") == "Researched" and (x.get("decision") or {}).get("decision") != "SOURCE NEEDED"]
    recommended = [x for x in researched if (x.get("decision") or {}).get("decision") == "CONTACT"]
    monitor = [x for x in researched if (x.get("decision") or {}).get("decision") == "MONITOR"]
    skipped = [x for x in researched if (x.get("decision") or {}).get("decision") == "SKIP"]
    review = [x for x in researched if (x.get("decision") or {}).get("decision") not in {"CONTACT", "MONITOR", "SKIP"}]
    return {
        "workspace": workspace,
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


def workspace_index() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for workspace in list_workspaces():
        detail = workspace_detail(workspace["id"])
        counts = (detail or {}).get("counts") or {}
        out.append({**workspace, "counts": counts})
    return out
