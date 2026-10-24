from __future__ import annotations

import json
import re
from typing import Any

from .llm_provider import LLMProvider
from .research import enrich_commercial_signals, generate_actionable_intelligence
from .scoring import score_from_facts
from .source_quality import assess_source_quality


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return fallback


def _parts(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;/|]+", str(value or "")) if x.strip()]


def _size_range(value: str) -> tuple[int, int]:
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", str(value or ""))]
    if not nums:
        return 0, 10**9
    if "+" in str(value):
        return nums[0], 10**9
    if len(nums) == 1:
        return 0, nums[0]
    return min(nums[0], nums[1]), max(nums[0], nums[1])


def workspace_to_profile(workspace: dict[str, Any]) -> dict[str, Any]:
    industry = _parts(str(workspace.get("industry") or ""))
    keywords = _parts(str(workspace.get("keywords") or ""))
    region = str(workspace.get("region") or "").strip()
    audience = str(workspace.get("audience") or "Any").strip()
    min_size, max_size = _size_range(str(workspace.get("company_size") or ""))
    countries: list[str] = []
    if region and region.lower() not in {"europe", "eu", "european union"}:
        countries = _parts(region)
    required: list[str] = []
    if audience in {"B2B", "B2C"}:
        required.append(audience)
    offer = str(workspace.get("offer") or "").strip()
    return {
        "name": str(workspace.get("name") or "Workspace targeting"),
        "description": "Workspace-specific targeting profile generated from the user's prospecting criteria.",
        "offer_name": offer[:120] if offer else "Workspace offer",
        "offer_summary": offer,
        "value_proposition": offer,
        "target_roles": ["Head of Sales", "Growth Lead", "RevOps", "Marketing Lead", "Founder", "COO"],
        "desired_triggers": ["new market expansion", "new product launch", "sales hiring", "growth hiring", "partnership", "funding", "leadership change"],
        "geographies": [region] if region else [],
        "countries": countries,
        "industries": industry,
        "min_team_size": min_size,
        "max_team_size": max_size,
        "required_signals": required,
        "preferred_signals": keywords,
        "disqualifiers": ["consumer only"] if audience == "B2B" else [],
    }


def facts_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_summary": str(row.get("company_summary") or ""),
        "business_type": str(row.get("business_type") or ""),
        "services": _loads(row.get("services_json"), []),
        "target_customers": _loads(row.get("target_customers_json"), []),
        "target_roles": _loads(row.get("target_roles_json"), []),
        "markets": _loads(row.get("markets_json"), []),
        "proof_points": _loads(row.get("proof_points_json"), []),
        "verified_signals": _loads(row.get("verified_signals_json"), []),
        "commercial_signals": _loads(row.get("commercial_signals_json"), []),
    }


def _signal_value(signal: dict[str, Any]) -> int:
    try:
        return max(0, min(100, int(signal.get("signal_value") or 0)))
    except Exception:
        return 0


def _timing(commercial: list[dict[str, Any]]) -> int:
    values = sorted((_signal_value(x) for x in commercial if isinstance(x, dict)), reverse=True)
    if not values:
        return 20
    top = values[0]
    avg = sum(values[:3]) / min(3, len(values))
    timing = round(top * 0.68 + avg * 0.32)
    meaningful = [
        x for x in commercial
        if isinstance(x, dict)
        and _signal_value(x) >= 55
        and str(x.get("freshness") or "").lower() in {"current", "recent"}
    ]
    if len(meaningful) >= 3:
        timing += 10
    elif len(meaningful) >= 2:
        timing += 6
    return min(100, timing)


def _confidence(row: dict[str, Any], source_confidence: str) -> int:
    quality = str(row.get("quality_status") or "").lower()
    confidence = 90 if "ready" in quality else 75 if "partial" in quality else 60
    sc = source_confidence.lower()
    if sc == "medium":
        confidence = min(confidence, 75)
    elif sc == "low":
        confidence = min(confidence, 40)
    return confidence


def _decision(fit: int, timing: int, confidence: int, priority: int) -> str:
    if fit >= 62 and timing >= 55 and confidence >= 55 and priority >= 62:
        return "CONTACT"
    if fit >= 62 and confidence >= 55:
        return "MONITOR"
    if confidence >= 55 and ((fit >= 50 and timing >= 45) or priority >= 55):
        return "POTENTIAL"
    if fit < 45 and confidence >= 50:
        return "SKIP"
    return "POTENTIAL"


def _decision_reason(decision: str, fit: int, timing: int, confidence: int, priority: int) -> str:
    if decision == "CONTACT":
        return f"Strong fit ({fit}/100) and timely signals ({timing}/100) make this account worth contacting now."
    if decision == "MONITOR":
        return f"Fit is strong ({fit}/100), but timing is weak ({timing}/100); keep the account on watch for a better trigger."
    if decision == "POTENTIAL":
        if timing >= 60 and fit < 62:
            return f"Recent activity is strong ({timing}/100), but fit is only moderate ({fit}/100); promising, not top priority."
        if fit >= 50 and timing < 45:
            return f"The account has moderate fit ({fit}/100), but there is not enough timing evidence yet."
        if confidence < 65:
            return f"The account looks potentially relevant, but research confidence is only {confidence}/100."
        return f"The account is plausible, but its combined fit/timing priority ({priority}/100) is below recommendation level."
    return f"Research confidence is sufficient ({confidence}/100), but fit is too weak ({fit}/100) to justify outreach."


def build_workspace_intelligence(workspace: dict[str, Any], row: dict[str, Any], provider_name: str = "gemini", generate_outreach: bool = True) -> dict[str, Any]:
    source = assess_source_quality(row)
    if not source.get("score_allowed"):
        return {
            "decision": "SOURCE NEEDED", "fit": None, "timing": None, "confidence": 25, "priority": None,
            "fit_summary": "Workspace fit is unavailable until a stronger public corporate source is available.",
            "score_breakdown": [], "hypotheses": [], "suggested_angle": "", "personalized_opener": "", "email_draft": "",
            "workspace_name": str(workspace.get("name") or "Workspace"),
            "reason": str(source.get("reason") or "Insufficient public source quality."),
        }

    profile = workspace_to_profile(workspace)
    facts = facts_from_row(row)
    facts["commercial_signals"] = enrich_commercial_signals(list(facts.get("commercial_signals") or []), profile)
    fit, breakdown = score_from_facts(row, facts, profile)
    timing = _timing(list(facts.get("commercial_signals") or []))
    confidence = _confidence(row, str(source.get("confidence") or "Unknown"))
    priority = round(fit * 0.55 + timing * 0.35 + confidence * 0.10)
    decision = _decision(fit, timing, confidence, priority)
    decision_reason = _decision_reason(decision, fit, timing, confidence, priority)

    positives = [x for x in breakdown if int(x.get("points") or 0) > 0]
    positives.sort(key=lambda x: int(x.get("points") or 0), reverse=True)
    gaps = [x for x in breakdown if int(x.get("max_points") or 0) > 0 and int(x.get("points") or 0) == 0]
    fit_summary = (
        f"{fit}/100 fit to workspace '{workspace.get('name') or 'targeting'}'. "
        + ("Strongest evidence: " + "; ".join(str(x.get("criterion") or "") for x in positives[:3]) + ". " if positives else "")
        + ("Main gaps: " + "; ".join(str(x.get("criterion") or "") for x in gaps[:2]) + "." if gaps else "")
    ).strip()

    hypotheses: list[dict[str, Any]] = []
    suggested_angle = ""
    opener = ""
    email = ""
    intelligence_error = ""
    offer = str(workspace.get("offer") or "").strip()
    if generate_outreach and offer:
        provider = LLMProvider.from_env(provider_name)
        if provider.enabled:
            try:
                intel = generate_actionable_intelligence(str(row.get("company") or ""), facts, profile, provider)
                hypotheses = list(intel.get("hypotheses") or [])
                suggested_angle = str(intel.get("best_outreach_angle") or "").strip()
                opener = str(intel.get("personalized_opener") or "").strip()
                email = str(intel.get("email_draft") or "").strip()
                if str(intel.get("fit_summary") or "").strip():
                    fit_summary = str(intel.get("fit_summary") or "").strip()
            except Exception as exc:
                intelligence_error = f"{type(exc).__name__}: {str(exc)[:500]}"

    return {
        "decision": decision, "fit": fit, "timing": timing, "confidence": confidence, "priority": priority,
        "fit_summary": fit_summary, "score_breakdown": breakdown, "hypotheses": hypotheses,
        "suggested_angle": suggested_angle, "personalized_opener": opener, "email_draft": email,
        "workspace_name": str(workspace.get("name") or "Workspace"), "offer": offer,
        "intelligence_error": intelligence_error, "reason": decision_reason,
    }
