from __future__ import annotations

import json
from datetime import date
from typing import Any

from .fetcher import fetch_company_pages
from .llm_provider import LLMProvider
from .research import extract_company_facts, generate_actionable_intelligence, research_quality, enrich_commercial_signals
from .scoring import priority, score_from_facts
from .storage import get_company, update_company, get_icp, log_activity


def _loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _existing_pages(row: dict[str, Any]) -> list[dict[str, str]]:
    pages = _loads(str(row.get("source_pages_json", "")), [])
    if isinstance(pages, list) and pages:
        return pages
    text = str(row.get("source_text", "") or "").strip()
    url = str(row.get("source_url", "") or row.get("website", "") or "").strip()
    if text and url:
        return [{"url": url, "title": row.get("company", ""), "text": text, "status": "stored"}]
    signals = str(row.get("public_signals", "") or "").strip()
    if signals and url:
        return [{"url": url, "title": row.get("company", ""), "text": signals, "status": "manual signals only"}]
    return []


def analyze_company(company_id: int, fetch_live: bool = True, provider_name: str = "gemini", progress=None, generate_outreach_draft: bool = True) -> dict:
    if progress:
        progress("starting", "Preparing analysis…", 3)
    row = get_company(company_id)
    if not row:
        raise KeyError("Company not found")

    provider = LLMProvider.from_env(provider_name)
    source_url = str(row.get("website") or row.get("source_url") or "").strip()
    changes: dict[str, Any] = {"analysis_error": "", "personalization_mode": provider.name, "llm_model": provider.model or ""}

    pages = _existing_pages(row)
    if fetch_live:
        if not source_url:
            raise RuntimeError("Add a public company website before live analysis")
        try:
            pages, status = fetch_company_pages(source_url, max_pages=8, progress=progress)
            changes["fetch_status"] = status
            changes["source_pages_json"] = json.dumps(pages, ensure_ascii=False)
            changes["source_text"] = "\n\n".join(p.get("text", "")[:1800] for p in pages[:4])
            changes["source_url"] = pages[0]["url"] if pages else source_url
            if pages:
                changes["verified_on"] = date.today().isoformat()
        except Exception as exc:
            changes["fetch_status"] = f"error:{type(exc).__name__}: {str(exc)[:180]}"
            changes["analysis_error"] = str(exc)[:700]
            update_company(company_id, changes)
            raise

    if not pages:
        raise RuntimeError("No usable public page content is available for analysis")
    if not provider.enabled:
        raise RuntimeError(f"{provider.name} is not configured. Configure the provider in .env first.")

    try:
        if progress:
            progress("researching", f"Extracting evidence-backed facts from {len(pages)} page(s)… This analysis step is time-limited, so it will not hang indefinitely.", 50)
        facts = extract_company_facts(str(row.get("company", "")), str(row.get("website", "")), pages, provider)
        if progress:
            progress("scoring", "Validating evidence and calculating score…", 72)
        quality_status, quality_reason = research_quality(facts, pages)
        profile = get_icp()
        facts["commercial_signals"] = enrich_commercial_signals(list(facts.get("commercial_signals") or []), profile)
        merged = {**row, **changes}
        score, breakdown = score_from_facts(merged, facts, profile)
        positives = [b for b in breakdown if int(b.get("points", 0)) > 0]
        positives.sort(key=lambda x: int(x.get("points", 0)), reverse=True)
        gaps = [b for b in breakdown if int(b.get("max_points", 0) or 0) > 0 and int(b.get("points", 0)) == 0]
        deterministic_fit = (
            f"{score}/100 fit to '{profile.get('name','configured profile')}'. "
            + ("Strongest evidence: " + "; ".join(str(x.get("criterion", "")) for x in positives[:3]) + ". " if positives else "")
            + ("Main gaps: " + "; ".join(str(x.get("criterion", "")) for x in gaps[:2]) + "." if gaps else "")
        ).strip()
        signals = facts.get("verified_signals") or []
        proof = facts.get("proof_points") or []
        commercial = facts.get("commercial_signals") or []
        evidence_lines = [f"{s.get('fact','')} — {s.get('source_url','')}" for s in (signals + proof)]

        # Persist the factual layer first. This is valuable even if the separate
        # strategy/outreach call is unavailable or intentionally skipped in batch mode.
        changes.update({
            "research_score": score,
            "research_priority": priority(score),
            "evidence": "\n".join(evidence_lines),
            "company_summary": facts.get("company_summary", ""),
            "business_type": facts.get("business_type", ""),
            "services_json": json.dumps(facts.get("services", []), ensure_ascii=False),
            "target_customers_json": json.dumps(facts.get("target_customers", []), ensure_ascii=False),
            "target_roles_json": json.dumps(facts.get("target_roles", []), ensure_ascii=False),
            "markets_json": json.dumps(facts.get("markets", []), ensure_ascii=False),
            "proof_points_json": json.dumps(proof, ensure_ascii=False),
            "verified_signals_json": json.dumps(signals, ensure_ascii=False),
            "commercial_signals_json": json.dumps(commercial, ensure_ascii=False),
            "hypotheses_json": "[]",
            "fit_summary": deterministic_fit,
            "source_pages_json": json.dumps(pages, ensure_ascii=False),
            "score_breakdown_json": json.dumps(breakdown, ensure_ascii=False),
            "suggested_angle": "",
            "quality_status": quality_status,
            "quality_reason": quality_reason,
            "personalized_opener": "",
            "email_draft": "",
            "personalization_mode": f"llm:{provider.name}",
            "llm_model": provider.last_model or provider.model or "",
            "analysis_error": "",
        })
        update_company(company_id, changes)

        if quality_status != "Insufficient evidence" and generate_outreach_draft:
            try:
                if progress:
                    progress("outreach", "Turning verified facts into clearly labeled hypotheses and next actions…", 84)
                intel = generate_actionable_intelligence(str(row.get("company", "")), facts, profile, provider)
                changes["fit_summary"] = str(intel.get("fit_summary", "")).strip()
                changes["hypotheses_json"] = json.dumps(intel.get("hypotheses", []), ensure_ascii=False)
                changes["suggested_angle"] = str(intel.get("best_outreach_angle", "")).strip()
                changes["personalized_opener"] = str(intel.get("personalized_opener", "")).strip()
                changes["email_draft"] = str(intel.get("email_draft", "")).strip()
                changes["llm_model"] = provider.last_model or provider.model or ""
            except Exception as outreach_exc:
                changes["analysis_error"] = (
                    "Factual research completed and was saved, but the strategy/outreach layer is temporarily unavailable. "
                    f"{type(outreach_exc).__name__}: {str(outreach_exc)[:560]}"
                )
                update_company(company_id, changes)
                updated = get_company(company_id)
                assert updated is not None
                if progress:
                    progress("done", "Facts and score saved. Strategy layer is temporarily unavailable.", 100)
                return updated
    except Exception as exc:
        changes["analysis_error"] = f"{type(exc).__name__}: {str(exc)[:700]}"
        update_company(company_id, changes)
        raise

    updated = update_company(company_id, changes)
    try:
        log_activity(company_id, "research_completed", f"Research completed · {score}/100 fit", "real")
    except Exception:
        pass
    if progress:
        progress("done", "Analysis complete.", 100)
    assert updated is not None
    return updated


def recalculate_score(company_id: int) -> dict:
    row = get_company(company_id)
    if not row:
        raise KeyError("Company not found")
    facts = {
        "company_summary": str(row.get("company_summary", "")),
        "business_type": str(row.get("business_type", "")),
        "services": _loads(str(row.get("services_json", "")), []),
        "target_customers": _loads(str(row.get("target_customers_json", "")), []),
        "target_roles": _loads(str(row.get("target_roles_json", "")), []),
        "markets": _loads(str(row.get("markets_json", "")), []),
        "proof_points": _loads(str(row.get("proof_points_json", "")), []),
        "verified_signals": _loads(str(row.get("verified_signals_json", "")), []),
        "commercial_signals": _loads(str(row.get("commercial_signals_json", "")), []),
    }
    profile = get_icp()
    facts["commercial_signals"] = enrich_commercial_signals(list(facts.get("commercial_signals") or []), profile)
    score, breakdown = score_from_facts(row, facts, profile)
    updated = update_company(company_id, {
        "research_score": score,
        "research_priority": priority(score),
        "score_breakdown_json": json.dumps(breakdown, ensure_ascii=False),
        "commercial_signals_json": json.dumps(facts.get("commercial_signals", []), ensure_ascii=False),
    })
    assert updated is not None
    return updated
