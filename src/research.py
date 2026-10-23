from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from .llm_provider import LLMProvider

EVIDENCE_ITEM = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "fact": {"type": "string"},
        "evidence": {"type": "string", "description": "Short verbatim or near-verbatim evidence from the supplied page."},
        "source_url": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["category", "fact", "evidence", "source_url", "confidence"],
}

SIGNAL_ITEM = {
    "type": "object",
    "properties": {
        "signal_type": {"type": "string", "description": "One of: hiring, product, partnership, acquisition, funding, customer_proof, expansion, pricing, technology_investment, market_focus, other."},
        "fact": {"type": "string"},
        "why_relevant": {"type": "string", "description": "Why this observable signal may matter commercially. Must stay cautious and not claim buying intent."},
        "evidence": {"type": "string"},
        "source_url": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "observed_date": {"type": "string", "description": "ISO date YYYY-MM-DD only when the supplied page explicitly supports the date; otherwise empty string."},
    },
    "required": ["signal_type", "fact", "why_relevant", "evidence", "source_url", "confidence", "observed_date"],
}

FACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "company_summary": {"type": "string", "description": "Factual 1-2 sentence summary based only on supplied pages."},
        "business_type": {"type": "string"},
        "services": {"type": "array", "items": {"type": "string"}, "maxItems": 7},
        "target_customers": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "target_roles": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "markets": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "proof_points": {"type": "array", "items": EVIDENCE_ITEM, "maxItems": 5},
        "verified_signals": {"type": "array", "items": EVIDENCE_ITEM, "maxItems": 7},
        "commercial_signals": {"type": "array", "items": SIGNAL_ITEM, "maxItems": 5},
    },
    "required": [
        "company_summary", "business_type", "services", "target_customers", "target_roles",
        "markets", "proof_points", "verified_signals", "commercial_signals"
    ],
}

INTELLIGENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fit_summary": {"type": "string", "description": "2-3 sentences explaining why the company does or does not fit the configured offer/ICP."},
        "hypotheses": {
            "type": "array", "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "based_on": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                    "target_role": {"type": "string"},
                    "confidence": {"type": "string", "description": "low, medium, or high"},
                    "recommended_action": {"type": "string"},
                },
                "required": ["title", "rationale", "based_on", "target_role", "confidence", "recommended_action"],
            },
        },
        "best_outreach_angle": {"type": "string"},
        "personalized_opener": {"type": "string"},
        "email_draft": {"type": "string"},
    },
    "required": ["fit_summary", "hypotheses", "best_outreach_angle", "personalized_opener", "email_draft"],
}


def _pages_prompt(pages: list[dict[str, str]]) -> str:
    chunks: list[str] = []
    for i, p in enumerate(pages[:8], 1):
        text = (p.get("text") or "")[:5200]
        chunks.append(f"[PAGE {i}]\nURL: {p.get('url','')}\nTITLE: {p.get('title','')}\nCONTENT:\n{text}")
    return "\n\n".join(chunks)


def extract_company_facts(company: str, website: str, pages: list[dict[str, str]], provider: LLMProvider) -> dict[str, Any]:
    if not provider.enabled:
        raise RuntimeError(f"{provider.name} is not configured")
    prompt = f'''You are a senior B2B sales-intelligence researcher. Extract decision-useful company information using ONLY the supplied official public pages.

Company: {company}
Website: {website}

GOAL:
Create a factual research layer that a marketer or BDR could use before deciding whether to spend time on this account. Do NOT write outreach yet.

STRICT FACT / SIGNAL RULES:
- Never infer buying intent, budget, pain, revenue, funding, headcount or internal priorities unless explicitly stated.
- Every proof point, verified signal and commercial signal MUST cite one of the supplied URLs exactly and include traceable evidence.
- Evidence should be short (preferably under 22 words) and closely match source wording.
- If unknown, return an empty string/array instead of guessing.
- Distinguish durable FACTS from COMMERCIAL SIGNALS. A commercial signal is an observable event/state that may affect timing (e.g. hiring for AI, launching a product, expansion, partnership, customer proof, pricing change). It is NOT proof of buying intent.
- Do not call generic slogans, navigation, SEO copy, training pages or unrelated blog posts a signal.
- For each commercial signal, set observed_date only when an explicit publication/event date is supported by the supplied page. Use YYYY-MM-DD. Otherwise use an empty string.
- Acquisition, funding, product launches, expansion, material pricing changes, relevant hiring, and active technology investment are generally more decision-useful than generic compliance statements or old partnerships. Still record the fact neutrally; ranking is handled by code.
- For target_roles, include roles only when a page explicitly addresses or names them (e.g. CTO, FinOps, CFO, RevOps).
- For proof_points, prefer concrete metrics, named customers, certifications, partner tiers, case-study results, retention claims or quantified outcomes.
- Keep company_summary to 2 concise sentences; services <=7; target_customers <=6; target_roles <=6; markets <=6; proof_points <=5; verified_signals <=7; commercial_signals <=5.

OFFICIAL PAGES:
{_pages_prompt(pages)}'''
    result = provider.generate_json(prompt, FACT_SCHEMA, temperature=0.0, max_tokens=3800)
    return validate_facts(result, pages)


def _norm(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _evidence_supported(evidence: str, page_text: str) -> bool:
    ev = _norm(evidence)
    if not ev:
        return False
    hay = set(_norm(page_text))
    overlap = sum(1 for t in ev if t in hay) / len(ev)
    return overlap >= 0.70


def _validated_items(items: Any, page_map: dict[str, str], *, signal: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("source_url", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        if url not in page_map or not evidence or not _evidence_supported(evidence, page_map[url]):
            continue
        base = {
            "fact": str(item.get("fact", "")).strip()[:520],
            "evidence": evidence[:450],
            "source_url": url,
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 0) or 0))),
        }
        if signal:
            base.update({
                "signal_type": str(item.get("signal_type", "other")).strip()[:60] or "other",
                "why_relevant": str(item.get("why_relevant", "")).strip()[:520],
                "observed_date": str(item.get("observed_date", "")).strip()[:10],
            })
        else:
            base["category"] = str(item.get("category", "Other")).strip()[:80]
        if base["fact"]:
            out.append(base)
    return out



def _parse_signal_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _freshness(observed_date: str, today: date | None = None) -> tuple[str, float, int | None]:
    dt = _parse_signal_date(observed_date)
    if dt is None:
        return "unknown", 0.65, None
    now = today or date.today()
    days = max(0, (now - dt).days)
    if days <= 120:
        return "current", 1.0, days
    if days <= 365:
        return "recent", 0.78, days
    return "dated", 0.25, days


def _base_signal_strength(signal: dict[str, Any]) -> tuple[str, int]:
    kind = str(signal.get("signal_type", "other")).lower()
    fact = str(signal.get("fact", "")).lower()
    high = {"acquisition", "funding", "expansion", "pricing", "technology_investment"}
    medium = {"hiring", "product", "partnership"}
    if kind in high:
        return "high", 85
    if kind == "product" and any(x in fact for x in ["launch", "launched", "release", "released", "announc", "new product", "new platform"]):
        return "high", 82
    if kind == "hiring" and any(x in fact for x in ["multiple", "team", "roles", "positions", "hiring for"]):
        return "medium", 68
    if kind in medium:
        return "medium", 62
    if kind in {"customer_proof", "market_focus"}:
        return "low", 38
    return "low", 30


def _profile_tokens(profile: dict[str, Any]) -> set[str]:
    pieces = [
        str(profile.get("offer_name", "")), str(profile.get("offer_summary", "")),
        str(profile.get("value_proposition", "")),
        " ".join(str(x) for x in (profile.get("target_roles") or [])),
        " ".join(str(x) for x in (profile.get("industries") or [])),
        " ".join(str(x) for x in (profile.get("preferred_signals") or [])),
        " ".join(str(x) for x in (profile.get("desired_triggers") or [])),
    ]
    stop = {"the","and","for","with","that","this","from","into","using","help","helps","company","companies","business","b2b","our","your","you","we","to","of","in","a","an"}
    return {x for x in re.findall(r"[a-z0-9]+", " ".join(pieces).lower()) if len(x) >= 3 and x not in stop}


def enrich_commercial_signals(signals: list[dict[str, Any]], profile: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    """Rank observable signals deterministically for sales usefulness.

    The model extracts fact/date/evidence. Code assigns strength, freshness and
    offer relevance so hypotheses do not depend on opaque model judgment.
    """
    offer_tokens = _profile_tokens(profile)
    desired = [str(x).lower() for x in (profile.get("desired_triggers") or []) if str(x).strip()]
    out: list[dict[str, Any]] = []
    for raw in signals or []:
        s = dict(raw)
        strength, base_score = _base_signal_strength(s)
        freshness, fresh_mult, age_days = _freshness(str(s.get("observed_date", "")), today=today)
        signal_text = " ".join([str(s.get("signal_type", "")), str(s.get("fact", "")), str(s.get("why_relevant", ""))]).lower()
        tokens = {x for x in re.findall(r"[a-z0-9]+", signal_text) if len(x) >= 3}
        overlap = offer_tokens & tokens
        desired_match = [d for d in desired if d in signal_text]
        if desired_match or len(overlap) >= 3:
            relevance, relevance_mult = "high", 1.0
        elif len(overlap) >= 1:
            relevance, relevance_mult = "medium", 0.65
        else:
            relevance, relevance_mult = "low", 0.25
        value = round(base_score * fresh_mult * relevance_mult)
        # Dated or irrelevant signals are retained as facts but cannot drive a strong opportunity.
        eligible = strength in {"high", "medium"} and freshness in {"current", "recent", "unknown"} and relevance in {"high", "medium"} and value >= 25
        s.update({
            "strength": strength,
            "freshness": freshness,
            "age_days": age_days,
            "offer_relevance": relevance,
            "signal_value": value,
            "hypothesis_eligible": eligible,
        })
        out.append(s)
    out.sort(key=lambda x: int(x.get("signal_value", 0)), reverse=True)
    return out

def validate_facts(result: dict[str, Any], pages: list[dict[str, str]]) -> dict[str, Any]:
    page_map = {p.get("url", ""): p.get("text", "") for p in pages}
    verified = _validated_items(result.get("verified_signals"), page_map, signal=False)
    proof = _validated_items(result.get("proof_points"), page_map, signal=False)
    commercial = _validated_items(result.get("commercial_signals"), page_map, signal=True)

    return {
        "company_summary": str(result.get("company_summary", "")).strip()[:1000],
        "business_type": str(result.get("business_type", "")).strip()[:240],
        "services": [str(x).strip()[:190] for x in (result.get("services") or []) if str(x).strip()][:7],
        "target_customers": [str(x).strip()[:190] for x in (result.get("target_customers") or []) if str(x).strip()][:6],
        "target_roles": [str(x).strip()[:160] for x in (result.get("target_roles") or []) if str(x).strip()][:6],
        "markets": [str(x).strip()[:160] for x in (result.get("markets") or []) if str(x).strip()][:6],
        "proof_points": proof[:5],
        "verified_signals": verified[:7],
        "commercial_signals": commercial[:5],
    }


def research_quality(facts: dict[str, Any], pages: list[dict[str, str]]) -> tuple[str, str]:
    n = len(facts.get("verified_signals") or []) + len(facts.get("proof_points") or [])
    if facts.get("company_summary") and n >= 3 and len(pages) >= 2:
        return "Ready for review", f"{n} evidence-backed facts across {len(pages)} public page(s)."
    if facts.get("company_summary") and n >= 1:
        return "Partial — manual review", f"Only {n} validated fact(s); more evidence is recommended before action."
    return "Insufficient evidence", "The crawler/LLM did not find enough traceable facts for a decision-useful brief."


def generate_actionable_intelligence(company: str, facts: dict[str, Any], profile: dict[str, Any], provider: LLMProvider) -> dict[str, Any]:
    ranked_signals = enrich_commercial_signals(list(facts.get("commercial_signals") or []), profile)
    eligible_signals = [s for s in ranked_signals if s.get("hypothesis_eligible")][:4]
    safe_payload = {
        "company": company,
        "company_summary": facts.get("company_summary", ""),
        "business_type": facts.get("business_type", ""),
        "services": facts.get("services", []),
        "target_customers": facts.get("target_customers", []),
        "target_roles": facts.get("target_roles", []),
        "markets": facts.get("markets", []),
        "proof_points": facts.get("proof_points", []),
        "verified_signals": facts.get("verified_signals", []),
        "commercial_signals": ranked_signals,
        "hypothesis_eligible_signals": eligible_signals,
    }
    profile_payload = {
        "offer_name": profile.get("offer_name", ""),
        "offer_summary": profile.get("offer_summary", ""),
        "value_proposition": profile.get("value_proposition", ""),
        "target_roles": profile.get("target_roles", []),
        "industries": profile.get("industries", []),
        "countries": profile.get("countries", []),
        "desired_triggers": profile.get("desired_triggers", []),
        "disqualifiers": profile.get("disqualifiers", []),
    }
    prompt = f'''You are a careful B2B account strategist. Convert verified company research into actionable, clearly labeled intelligence for the configured offer.

CONFIGURED OFFER / ICP:
{json.dumps(profile_payload, ensure_ascii=False, indent=2)}

VERIFIED COMPANY RESEARCH:
{json.dumps(safe_payload, ensure_ascii=False, indent=2)}

RULES:
- Facts remain facts. Hypotheses MUST be explicitly cautious and must never be written as known company pain or buying intent.
- Every hypothesis must list the exact verified fact/signal text it is based on in based_on.
- Hypotheses may be driven ONLY by hypothesis_eligible_signals. Do not build an opportunity from a dated, low-strength, or low-relevance signal.
- If hypothesis_eligible_signals is empty, return zero hypotheses and keep best_outreach_angle factual/conservative.
- Prefer HIGH strength + CURRENT/RECENT + HIGH/MEDIUM offer relevance.
- An old partnership, generic compliance policy, customer proof, or general market statement may support context but must not become the main sales opportunity by itself.
- If there is weak evidence of relevance, say so in fit_summary and return fewer hypotheses.
- best_outreach_angle must connect the configured offer to a VERIFIED fact or commercial signal; never merely restate what the company itself sells.
- Do not invent employee names, budgets, priorities, projects, pain, tech stack or performance metrics.
- personalized_opener: 20-35 words, human, specific, no hype.
- email_draft: under 120 words, non-pushy, editable, and include a simple subject line.
- No mention of scraping, scoring, LLMs, this portfolio project or internal workflow.
'''
    return provider.generate_json(prompt, INTELLIGENCE_SCHEMA, temperature=0.15, max_tokens=2200)


def generate_outreach(company: str, facts: dict[str, Any], provider: LLMProvider, profile: dict[str, Any] | None = None) -> tuple[str, str]:
    intelligence = generate_actionable_intelligence(company, facts, profile or {}, provider)
    return str(intelligence.get("personalized_opener", "")).strip(), str(intelligence.get("email_draft", "")).strip()
