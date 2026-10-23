from __future__ import annotations

from typing import Any

from .change_tracking import record_snapshot
from .service_core import analyze_company as _core_analyze_company
from .service_core import recalculate_score as _core_recalculate_score
from .source_quality import assess_source_quality
from .storage import get_company, log_activity, update_company


def _record(company_id: int, row: dict[str, Any]) -> dict[str, Any]:
    try:
        record_snapshot(company_id, row)
    except Exception:
        pass
    return row


def _apply_source_quality(company_id: int, row: dict[str, Any]) -> dict[str, Any]:
    assessment = assess_source_quality(row)
    if assessment.get("score_allowed"):
        return row

    reason = str(assessment.get("reason") or "Insufficient public access for reliable scoring.")
    source_type = str(assessment.get("source_type") or "limited public source")
    confidence = str(assessment.get("confidence") or "Low")
    changes = {
        "quality_status": "Limited public access",
        "quality_reason": reason,
        "research_score": 0,
        "research_priority": "",
        "fit_summary": f"Fit score unavailable. Source quality: {source_type}. Research confidence: {confidence}. {reason}",
        "score_breakdown_json": "[]",
        "hypotheses_json": "[]",
        "suggested_angle": "",
        "personalized_opener": "",
        "email_draft": "",
    }
    updated = update_company(company_id, changes)
    if updated is None:
        updated = row
    try:
        log_activity(company_id, "research_limited", f"Research saved without a fit score · {source_type}", "real")
    except Exception:
        pass
    return updated


def analyze_company(company_id: int, fetch_live: bool = True, provider_name: str = "gemini", progress=None, generate_outreach_draft: bool = True) -> dict:
    try:
        result = _core_analyze_company(
            company_id,
            fetch_live=fetch_live,
            provider_name=provider_name,
            progress=progress,
            generate_outreach_draft=generate_outreach_draft,
        )
    except RuntimeError as exc:
        text = str(exc).lower()
        if "no usable public page content" not in text:
            raise
        row = get_company(company_id)
        if not row:
            raise
        updated = update_company(company_id, {
            "quality_status": "Limited public access",
            "quality_reason": "No usable public page content was accessible from this domain. Try an official corporate, newsroom, investor-relations, or company-information source.",
            "research_score": 0,
            "research_priority": "",
            "fit_summary": "Fit score unavailable because the submitted domain did not expose enough public company information for evidence-backed scoring.",
            "score_breakdown_json": "[]",
            "hypotheses_json": "[]",
            "suggested_angle": "",
            "personalized_opener": "",
            "email_draft": "",
            "analysis_error": "",
        })
        if progress:
            progress("done", "Public access is too limited for a reliable fit score. Saved as N/A.", 100)
        return _record(company_id, updated or row)
    final = _apply_source_quality(company_id, result)
    return _record(company_id, final)


def recalculate_score(company_id: int) -> dict:
    row = get_company(company_id)
    if not row:
        raise KeyError("Company not found")
    assessment = assess_source_quality(row)
    if not assessment.get("score_allowed"):
        return _apply_source_quality(company_id, row)
    return _core_recalculate_score(company_id)
