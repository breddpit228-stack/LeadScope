from __future__ import annotations

import re
from typing import Any

EUROPE_COUNTRIES = {
    "albania", "andorra", "austria", "belarus", "belgium", "bosnia and herzegovina", "bulgaria",
    "croatia", "cyprus", "czech republic", "czechia", "denmark", "estonia", "finland", "france",
    "germany", "greece", "hungary", "iceland", "ireland", "italy", "kosovo", "latvia",
    "liechtenstein", "lithuania", "luxembourg", "malta", "moldova", "monaco", "montenegro",
    "netherlands", "north macedonia", "norway", "poland", "portugal", "romania", "san marino",
    "serbia", "slovakia", "slovenia", "spain", "sweden", "switzerland", "ukraine",
    "united kingdom", "uk", "vatican city",
}

B2B_MARKERS = (
    " b2b ", "businesses", "companies", "enterprise", "enterprises", "merchants", "employers",
    "organisations", "organizations", "professionals", "accountants", "developers", "smes", "sme ",
    "small businesses", "business customers", "corporate customers", "commercial customers",
    "business banking", "corporate banking", "business clients", "enterprise clients",
)
B2C_MARKERS = (
    "consumers", "consumer", "individuals", "individual clients", "personal customers", "households",
    "personal banking", "retail banking", "personal finance", "personal loans", "personal accounts",
    "private customers", "individual customers", "for individuals", "personal use",
)


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


def _region_matches(region: str, country: str, city: str = "") -> bool:
    target = str(region or "").strip().lower()
    country_l = str(country or "").strip().lower()
    location = f"{country_l} {str(city or '').strip().lower()}".strip()
    if target in {"europe", "eu", "european union"}:
        return country_l in EUROPE_COUNTRIES
    return bool(target and target in location)


def _infer_audience(profile: dict[str, Any]) -> tuple[str, str]:
    current = str(profile.get("audience") or "").strip()
    text = " " + " ".join([
        str(profile.get("description") or ""),
        str(profile.get("company_type") or ""),
        str(profile.get("category") or ""),
    ]).lower() + " "
    b2b = any(marker in text for marker in B2B_MARKERS)
    b2c = any(marker in text for marker in B2C_MARKERS)

    if b2b and b2c:
        return "Mixed B2B/B2C", "Public profile contains both business and consumer signals."
    if b2b:
        return "B2B", "Public profile contains business-customer signals."
    if b2c:
        return "B2C", "Public profile contains consumer/individual-customer signals."
    if current.lower() in {"b2b", "b2c", "mixed b2b/b2c"}:
        return current, "Existing company classification."
    return "Unknown", "Business model is not verified from the basic public profile."


def _requirement(key: str, label: str, status: str, value: str, target: str, reason: str, role: str) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "value": value,
        "target": target,
        "reason": reason,
        "role": role,
    }


def apply_strict_match(
    base: dict[str, Any],
    profile: dict[str, Any],
    workspace: dict[str, Any],
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make Discover evidence-aware without confusing missing data with a mismatch.

    Industry and geography are the core retrieval criteria. Audience and company size are
    supporting criteria: verified contradictions demote the account, but unknown public
    data only lowers confidence and remains visible as `?` in the UI.
    """
    out = dict(base or {})
    raw_score = max(0, min(100, int(out.get("score") or 0)))
    requirements: list[dict[str, str]] = []
    gaps = list(out.get("gaps") or [])
    base_matched = list(out.get("matched") or [])

    industry = str(workspace.get("industry") or "").strip()
    relation = dict(out.get("industry_relation") or {})
    if industry:
        kind = str(relation.get("kind") or "none")
        industry_points = int(out.get("industry_points") or 0)
        # A taxonomy-only 36/40 hit is useful for retrieval, but does not prove primary industry.
        taxonomy_only = kind == "primary" and industry_points == 36
        if kind == "primary" and industry_points >= 30 and not taxonomy_only:
            status = "match"
            industry_reason = str(relation.get("label") or f"Primary industry · {industry}")
        elif taxonomy_only:
            status = "partial"
            industry_reason = f"Taxonomy suggests {industry}, but the public description does not confirm it yet."
        elif kind in {"adjacent", "serves"}:
            status = "partial"
            industry_reason = str(relation.get("label") or f"Adjacent to {industry}")
        else:
            status = "mismatch"
            industry_reason = str(relation.get("label") or "No convincing primary-industry evidence.")
        requirements.append(_requirement(
            "industry", "Industry", status,
            str(relation.get("label") or "Not verified"), industry,
            industry_reason, "core",
        ))

    region = str(workspace.get("region") or "").strip()
    if region:
        country = str(profile.get("country") or "").strip()
        city = str(profile.get("city") or "").strip()
        if not country:
            status = "unknown"
            reason = "Country is not verified."
        elif _region_matches(region, country, city):
            status = "match"
            reason = f"Verified location: {country}."
        else:
            status = "mismatch"
            reason = f"Verified location ({country}) does not match {region}."
        requirements.append(_requirement("location", "Location", status, country or "Unknown", region, reason, "core"))

    audience_target = str(workspace.get("audience") or "Any").strip()
    if audience_target and audience_target.lower() != "any":
        audience_value, audience_reason = _infer_audience(profile)
        if audience_value.lower() == audience_target.lower():
            status = "match"
        elif audience_value.lower() == "mixed b2b/b2c" and audience_target.lower() in {"b2b", "b2c"}:
            status = "partial"
        elif audience_value.lower() == "unknown":
            status = "unknown"
        else:
            status = "mismatch"
        requirements.append(_requirement(
            "audience", "Business model", status, audience_value, audience_target,
            audience_reason, "supporting",
        ))
        profile["audience"] = audience_value

    size_target = str(workspace.get("company_size") or "").strip()
    if size_target:
        actual_text = str(profile.get("team_size_public") or (row or {}).get("team_size_public") or "").strip()
        wanted = _range(size_target)
        actual = _range(actual_text)
        if not actual:
            status = "unknown"
            reason = "Company size is not verified."
        elif wanted and max(wanted[0], actual[0]) <= min(wanted[1], actual[1]):
            if actual[0] == actual[1] and wanted[0] <= actual[0] <= wanted[1]:
                status = "match"
            else:
                overlap = min(wanted[1], actual[1]) - max(wanted[0], actual[0]) + 1
                span = max(1, min(actual[1] - actual[0] + 1, wanted[1] - wanted[0] + 1))
                status = "match" if overlap / span >= 0.6 else "partial"
            reason = f"Public size evidence: {actual_text}."
        else:
            status = "mismatch"
            reason = f"Verified size ({actual_text}) does not match {size_target}."
        requirements.append(_requirement("size", "Company size", status, actual_text or "Unknown", size_target, reason, "supporting"))

    core = [r for r in requirements if r["role"] == "core"]
    supporting = [r for r in requirements if r["role"] == "supporting"]
    statuses = [r["status"] for r in requirements]
    unknowns = sum(1 for x in statuses if x == "unknown")
    partials = sum(1 for x in statuses if x == "partial")
    mismatches = sum(1 for x in statuses if x == "mismatch")
    supporting_unknowns = sum(1 for r in supporting if r["status"] == "unknown")
    supporting_mismatches = sum(1 for r in supporting if r["status"] == "mismatch")
    supporting_partials = sum(1 for r in supporting if r["status"] == "partial")

    score = raw_score
    industry_status = next((r["status"] for r in core if r["key"] == "industry"), "match")
    location_status = next((r["status"] for r in core if r["key"] == "location"), "match")

    # Core evidence determines whether the account belongs in the target market at all.
    if industry_status == "mismatch":
        score = min(score, 39)
    elif industry_status == "partial":
        score = min(score, 59)
    if location_status == "mismatch":
        score = min(score, 39)
    elif location_status == "unknown":
        score = min(score, 59)

    # Supporting criteria refine fit. Unknown is not a contradiction; verified mismatch is.
    if supporting_mismatches:
        score = min(score, 49)
    elif supporting_partials:
        score = min(score, 79)
    elif supporting_unknowns >= 2:
        score = min(score, 79)
    elif supporting_unknowns == 1:
        score = min(score, 84)

    core_complete = bool(core) and all(r["status"] == "match" for r in core)
    if not core:
        core_complete = True
    best = core_complete and supporting_mismatches == 0 and score >= 60 and (not industry or industry_status == "match")

    if best and supporting_unknowns:
        label = "Strong candidate · some data unverified" if score >= 74 else "Good candidate · some data unverified"
    elif best and score >= 88:
        label = "Excellent profile match"
    elif best and score >= 74:
        label = "Strong profile match"
    elif best:
        label = "Good profile match"
    elif any(r["status"] == "unknown" for r in core):
        label = "Promising but core data is incomplete"
    elif partials:
        label = "Broader profile match"
    elif mismatches:
        label = "Criteria mismatch"
    else:
        label = "Possible profile match" if score >= 42 else "Low profile match"

    marks = {"match": "✓", "partial": "~", "unknown": "?", "mismatch": "×"}
    requirement_summary = [f"{r['label']} {marks.get(r['status'], '?')}" for r in requirements]
    keyword_summary = [x for x in base_matched if str(x).startswith("Keywords")]
    for r in requirements:
        if r["status"] in {"unknown", "mismatch", "partial"} and r["reason"] not in gaps:
            gaps.append(r["reason"])

    out.update({
        "raw_score": raw_score,
        "score": score,
        "label": label,
        "tier": "best" if best else "broader",
        "requirements": requirements,
        "requirement_summary": requirement_summary,
        "required_complete": core_complete,
        "core_complete": core_complete,
        "supporting_complete": all(r["status"] == "match" for r in supporting) if supporting else True,
        "unknown_required": unknowns,
        "mismatched_required": mismatches,
        "partial_required": partials,
        "supporting_unknown": supporting_unknowns,
        "supporting_mismatch": supporting_mismatches,
        "matched": (requirement_summary + keyword_summary)[:5],
        "gaps": gaps[:8],
    })
    return out
