from __future__ import annotations

import re
from typing import Any

B2B_TERMS = ["b2b", "enterprise", "software house", "consulting", "custom software", "saas", "technology partner", "outsourcing", "business"]
PROOF_TERMS = ["case study", "case studies", "customers", "clients", "portfolio", "success story", "retention", "partner", "certified"]


def _contains(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(t and t.lower() in lowered for t in terms)


def _tokens(text: str) -> set[str]:
    stop = {"the","and","for","with","that","this","from","into","using","help","helps","teams","company","companies","business","b2b","we","our","your","to","of","in","a","an"}
    return {x for x in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(x) >= 3 and x not in stop}


def _team_number(value: str) -> int | None:
    nums = re.findall(r"\d+", (value or "").replace(",", ""))
    try:
        return int(nums[-1]) if nums else None
    except Exception:
        return None


def score_from_facts(row: dict[str, Any], facts: dict[str, Any], icp: dict[str, Any] | None = None) -> tuple[int, list[dict[str, Any]]]:
    """Explainable 0-100 fit score relative to the configured offer + ICP.

    Deliberately reserves points for timing evidence and team-size verification so an
    ordinary tech company cannot casually score 100/100.
    """
    icp = icp or {}
    signals = facts.get("verified_signals") or []
    commercial = facts.get("commercial_signals") or []
    proof = facts.get("proof_points") or []
    roles = [str(x) for x in (facts.get("target_roles") or [])]
    blob = " ".join([
        str(facts.get("business_type", "")),
        " ".join(facts.get("services") or []),
        " ".join(facts.get("target_customers") or []),
        " ".join(roles),
        " ".join(facts.get("markets") or []),
        " ".join(str(s.get("fact", "")) for s in signals),
        " ".join(str(s.get("fact", "")) for s in commercial),
        " ".join(str(s.get("fact", "")) for s in proof),
        str(row.get("segment", "")),
    ])
    score = 0
    breakdown: list[dict[str, Any]] = []

    def add(label: str, points: int, max_points: int, reason: str) -> None:
        nonlocal score
        score += points
        breakdown.append({"criterion": label, "points": points, "max_points": max_points, "reason": reason})

    disqualifiers = [str(x) for x in (icp.get("disqualifiers") or [])]
    matched_disq = [x for x in disqualifiers if x and x.lower() in blob.lower()]
    if matched_disq:
        add("Disqualifiers", -25, 0, f"Matched: {', '.join(matched_disq[:3])}.")

    # 1) Geography — 10
    countries = [str(x) for x in (icp.get("countries") or []) if str(x).strip()]
    country = str(row.get("country", "")).strip()
    markets = " ".join(facts.get("markets") or [])
    geo_blob = f"{country} {markets}".lower()
    if countries:
        matched = [c for c in countries if c.lower() in geo_blob]
        add("Geography fit", 10 if matched else 0, 10, f"Matched configured geography: {', '.join(matched[:3])}." if matched else "No configured target country was verified.")
    else:
        europe_terms = ["europe","eu","united kingdom","germany","poland","netherlands","spain","france","sweden","denmark","finland","belgium","czech","portugal","estonia","ireland","norway","switzerland","austria","italy"]
        matched = any(t in geo_blob for t in europe_terms)
        add("Geography fit", 10 if matched else 2, 10, "Verified Europe relevance." if matched else "Europe relevance is not clearly verified.")

    # 2) Industry/category — 15
    industries = [str(x) for x in (icp.get("industries") or []) if str(x).strip()]
    ind_matches = [x for x in industries if x.lower() in blob.lower()]
    ind_points = 15 if len(ind_matches) >= 2 else 10 if len(ind_matches) == 1 else 0
    add("Industry / category fit", ind_points, 15, f"Matched: {', '.join(ind_matches[:4])}." if ind_matches else "No configured category match was verified.")

    # 3) Required — 15
    required = [str(x) for x in (icp.get("required_signals") or []) if str(x).strip()]
    if required:
        matched = [x for x in required if x.lower() in blob.lower() or (x.lower() == "b2b" and _contains(blob, B2B_TERMS))]
        points = round(15 * len(matched) / len(required))
        add("Required fit", points, 15, f"Verified {len(matched)}/{len(required)} required signal(s): {', '.join(matched) or 'none'}.")
    else:
        add("Required fit", 10 if _contains(blob, B2B_TERMS) else 0, 15, "B2B relevance verified." if _contains(blob, B2B_TERMS) else "No required fit criteria configured.")

    # 4) Preferred — 10
    preferred = [str(x) for x in (icp.get("preferred_signals") or []) if str(x).strip()]
    pref_matches = [x for x in preferred if x.lower() in blob.lower()]
    pref_points = min(10, len(pref_matches) * 2)
    add("Preferred signals", pref_points, 10, f"Matched {len(pref_matches)}: {', '.join(pref_matches[:5])}." if pref_matches else "No preferred signal match.")

    # 5) Offer / role adjacency — 10
    offer_text = " ".join([str(icp.get("offer_summary", "")), str(icp.get("value_proposition", ""))])
    offer_overlap = _tokens(offer_text) & _tokens(blob)
    configured_roles = [str(x) for x in (icp.get("target_roles") or []) if str(x).strip()]
    role_matches = [r for r in configured_roles if any(tok in " ".join(roles).lower() for tok in _tokens(r))]
    adjacency = min(6, len(offer_overlap)) + (4 if role_matches else 0)
    add("Offer adjacency", min(10, adjacency), 10,
        (f"Offer-language overlap: {', '.join(sorted(list(offer_overlap))[:5]) or 'none'}; target role match: {', '.join(role_matches[:2]) or 'none'}."))

    # 6) Observable timing / commercial signal — 15
    # Signals are pre-ranked by deterministic strength × freshness × offer relevance.
    # Old/weak/irrelevant observations should not inflate account fit.
    if commercial:
        values = [max(0, min(100, int(s.get("signal_value", 0) or 0))) for s in commercial]
        strong = [s for s in commercial if s.get("strength") in {"high", "medium"} and s.get("offer_relevance") in {"high", "medium"}]
        current = [s for s in strong if s.get("freshness") in {"current", "recent"}]
        # Top signals matter most; several weak items cannot manufacture a high timing score.
        top = sorted(values, reverse=True)[:3]
        sig_points = round(min(15, sum(top) / 18)) if top else 0
        add("Commercial timing signals", sig_points, 15,
            f"{len(commercial)} observed signal(s); {len(strong)} medium/high-strength and offer-relevant; {len(current)} current/recent. Top signal values: {', '.join(map(str, top)) or 'none'}.")
    else:
        add("Commercial timing signals", 0, 15, "No evidence-backed timing/growth signal was found in this crawl.")

    # 7) Evidence quality — 10
    evidence_count = len(signals) + len(proof)
    evidence_points = 10 if evidence_count >= 6 else 8 if evidence_count >= 4 else 5 if evidence_count >= 2 else 2 if evidence_count == 1 else 0
    add("Evidence depth", evidence_points, 10, f"{evidence_count} traceable fact/proof item(s) survived source validation.")

    # 8) Public proof — 5
    proof_points = 5 if proof else 3 if _contains(blob, PROOF_TERMS) else 0
    add("Public proof", proof_points, 5, f"{len(proof)} explicit proof point(s) verified." if proof else "No concrete customer/metric/partner proof was extracted.")

    # 9) Team-size fit — 10
    size = _team_number(str(row.get("team_size_public", "")))
    if size is None:
        add("Team size", 0, 10, "Team size was not verified, so no fit points are awarded.")
    else:
        min_size = int(icp.get("min_team_size") or 0)
        max_size = int(icp.get("max_team_size") or 10**9)
        add("Team size", 10 if min_size <= size <= max_size else 0, 10,
            f"Verified size {size} {'fits' if min_size <= size <= max_size else 'falls outside'} configured range {min_size}-{max_size}.")

    return max(0, min(int(score), 100)), breakdown


def priority(score: int) -> str:
    if score >= 80:
        return "A — strong fit"
    if score >= 65:
        return "B — promising fit"
    if score >= 45:
        return "C — investigate"
    return "D — low fit"
