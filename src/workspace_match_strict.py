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


def _requirement(key: str, label: str, status: str, value: str, target: str, reason: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "value": value, "target": target, "reason": reason}


def apply_strict_match(
    base: dict[str, Any],
    profile: dict[str, Any],
    workspace: dict[str, Any],
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an arithmetic profile score into an evidence-aware Discover decision.

    The original matcher still supplies weighted scoring and industry relationship evidence.
    This layer prevents unknown or contradictory required criteria from appearing as a
    'Strong match'. It never invents missing company facts.
    """
    out = dict(base or {})
    raw_score = max(0, min(100, int(out.get("score") or 0)))
    requirements: list[dict[str, str]] = []
    gaps = list(out.get("gaps") or [])

    industry = str(workspace.get("industry") or "").strip()
    relation = dict(out.get("industry_relation") or {})
    if industry:
        kind = str(relation.get("kind") or "none")
        if kind == "primary" and int(out.get("industry_points") or 0) >= 30:
            status = "match"
        elif kind in {"adjacent", "serves"}:
            status = "partial"
        else:
            status = "mismatch"
        requirements.append(_requirement(
            "industry", "Industry", status,
            str(relation.get("label") or "Not verified"), industry,
            str(relation.get("label") or "No convincing primary-industry evidence."),
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
        requirements.append(_requirement("location", "Location", status, country or "Unknown", region, reason))

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
            audience_reason,
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
        requirements.append(_requirement("size", "Company size", status, actual_text or "Unknown", size_target, reason))

    statuses = [r["status"] for r in requirements]
    mismatches = sum(1 for x in statuses if x == "mismatch")
    unknowns = sum(1 for x in statuses if x == "unknown")
    partials = sum(1 for x in statuses if x == "partial")

    score = raw_score
    industry_status = next((r["status"] for r in requirements if r["key"] == "industry"), "match")
    if industry_status == "mismatch":
        score = min(score, 39)
    elif industry_status == "partial":
        score = min(score, 59)
    if mismatches:
        score = min(score, 49)
    if unknowns >= 2:
        score = min(score, 59)
    elif unknowns == 1:
        score = min(score, 69)
    if partials and not mismatches and not unknowns:
        score = min(score, 79)

    all_required_match = bool(requirements) and all(r["status"] == "match" for r in requirements)
    if not requirements:
        all_required_match = True
    best = all_required_match and score >= 60 and (not industry or industry_status == "match")

    if best and score >= 88:
        label = "Excellent profile match"
    elif best and score >= 74:
        label = "Strong profile match"
    elif best:
        label = "Good profile match"
    elif unknowns:
        label = "Promising but incomplete"
    elif partials:
        label = "Broader profile match"
    elif mismatches:
        label = "Criteria mismatch"
    else:
        label = "Possible profile match" if score >= 42 else "Low profile match"

    marks = {"match": "✓", "partial": "~", "unknown": "?", "mismatch": "×"}
    requirement_summary = [f"{r['label']} {marks.get(r['status'], '?')}" for r in requirements]
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
        "required_complete": all_required_match,
        "unknown_required": unknowns,
        "mismatched_required": mismatches,
        "partial_required": partials,
        "gaps": gaps[:8],
    })
    return out
