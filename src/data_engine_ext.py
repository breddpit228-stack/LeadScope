from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .change_tracking import get_last_changes
from .data_engine import company_profile as _base_company_profile
from .data_engine import summarize_library


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _evidence_freshness(row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    timeline = profile.get("timeline") or []
    dated: list[tuple[int, str]] = []
    for item in timeline:
        if not isinstance(item, dict):
            continue
        parsed = _parse_date(item.get("date"))
        if parsed:
            dated.append(((today - parsed).days, str(item.get("title") or item.get("type") or "Evidence")))

    research_date = _parse_date(row.get("verified_on"))
    research_age = (today - research_date).days if research_date else None
    if not dated:
        return {
            "label": "Unknown",
            "age_days": None,
            "fresh_count": 0,
            "recent_count": 0,
            "historical_count": 0,
            "research_age_days": research_age,
        }

    age = min(x[0] for x in dated)
    if age <= 90:
        label = "Fresh"
    elif age <= 365:
        label = "Recent"
    elif age <= 730:
        label = "Aging"
    else:
        label = "Historical"
    return {
        "label": label,
        "age_days": age,
        "fresh_count": sum(1 for days, _ in dated if days <= 90),
        "recent_count": sum(1 for days, _ in dated if 90 < days <= 365),
        "historical_count": sum(1 for days, _ in dated if days > 730),
        "research_age_days": research_age,
    }


def _buying_committee(profile: dict[str, Any]) -> list[dict[str, str]]:
    roles = [str(x).strip() for x in (profile.get("buying_roles") or []) if str(x).strip()]
    out: list[dict[str, str]] = []
    for role in roles[:6]:
        low = role.lower()
        if any(x in low for x in ["revops", "operations", "ops"]):
            why = "Likely owner of workflow, CRM or research-process efficiency."
        elif any(x in low for x in ["growth", "marketing"]):
            why = "Likely beneficiary of faster targeting, segmentation and account research."
        elif any(x in low for x in ["sales", "commercial", "revenue"]):
            why = "Likely owner of pipeline quality, account prioritization or outbound execution."
        elif any(x in low for x in ["founder", "ceo", "coo"]):
            why = "Potential executive sponsor for productivity or go-to-market improvement."
        else:
            why = "Public evidence suggests this role is relevant to the account opportunity."
        out.append({"role": role, "why": why})
    return out


def _angles(profile: dict[str, Any]) -> list[dict[str, Any]]:
    existing = [str(x).strip() for x in (profile.get("angles") or []) if str(x).strip()]
    timeline = [x for x in (profile.get("timeline") or []) if isinstance(x, dict)]
    candidates: list[tuple[str, str, int]] = []
    for title in existing:
        candidates.append((title, "Generated from the researched opportunity hypothesis.", 85))
    types = " ".join(str(x.get("type") or "").lower() for x in timeline[:6])
    if any(x in types for x in ["launch", "product", "expansion"]):
        candidates.append(("Support product or market expansion", "Recent product/expansion evidence creates a concrete reason to discuss scalable account research.", 76))
    if any(x in types for x in ["hiring", "career", "team"]):
        candidates.append(("Reduce manual work during team growth", "Hiring or team-growth signals may increase the cost of manual qualification and research.", 66))
    if any(x in types for x in ["partner", "partnership", "ecosystem"]):
        candidates.append(("Prioritize accounts around ecosystem growth", "Partnership activity can broaden the account universe and make prioritization more valuable.", 62))
    if not candidates and profile.get("data_level") == "Researched":
        candidates.append(("Improve account research efficiency", "The account is researched, but no stronger signal-specific angle is supported yet.", 45))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for title, rationale, strength in sorted(candidates, key=lambda x: -x[2]):
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append({"title": title, "rationale": rationale, "strength": strength, "recommended": len(unique) == 0})
        if len(unique) >= 3:
            break
    return unique


def company_profile(row: dict[str, Any], icp: dict[str, Any]) -> dict[str, Any]:
    profile = _base_company_profile(row, icp)

    # A known storefront/social domain should request a better source immediately,
    # even before a deep research run. Do not tell the user merely to "Research" it.
    source = profile.get("source") or {}
    if source.get("status") == "Needs better source":
        profile["decision"] = {
            "decision": "SOURCE NEEDED",
            "fit": None,
            "timing": None,
            "confidence": 20,
            "priority": None,
            "reason": source.get("reason") or "Use a better corporate source before scoring this company.",
        }

    # Change snapshots only exist after deep research. Avoid one SQLite lookup for
    # every Indexed company when rendering a 10k-company Discover library.
    company_id = int(row.get("id") or 0)
    changes = get_last_changes(company_id) if company_id and profile.get("data_level") == "Researched" else []
    profile["changes"] = changes
    profile["changes_count"] = len(changes)
    profile["evidence_freshness"] = _evidence_freshness(row, profile)
    profile["buying_committee"] = _buying_committee(profile)
    profile["outreach_angles"] = _angles(profile)
    return profile


__all__ = ["company_profile", "summarize_library"]
