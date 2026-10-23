from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

SOCIAL_OR_LOGIN_HEAVY = {
    "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "tiktok.com", "pinterest.com", "snapchat.com",
}

MARKETPLACE_OR_STOREFRONT = {
    "amazon.com", "amazon.co.uk", "amazon.de", "amazon.fr", "amazon.it", "amazon.es",
    "ebay.com", "etsy.com", "aliexpress.com", "walmart.com",
}


def _host(value: str) -> str:
    try:
        host = (urlparse(value or "").hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _pages(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = row.get("source_pages_json") or "[]"
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    try:
        parsed = json.loads(str(value))
        return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []
    except Exception:
        return []


def assess_source_quality(row: dict[str, Any]) -> dict[str, Any]:
    """Return whether the public source is strong enough for a defensible fit score.

    This is deliberately conservative. A low-access source should produce N/A, not a
    misleading 0/100. The caller may still keep any factual snippets that were found.
    """
    website = str(row.get("website") or row.get("source_url") or "")
    host = _host(website)
    pages = _pages(row)
    texts = [str(p.get("text") or "").strip() for p in pages]
    total_chars = sum(len(t) for t in texts)
    meaningful_pages = sum(1 for t in texts if len(t) >= 350)
    quality_status = str(row.get("quality_status") or "").strip().lower()

    if host in SOCIAL_OR_LOGIN_HEAVY:
        return {
            "score_allowed": False,
            "source_type": "login-heavy / social platform",
            "confidence": "Low",
            "reason": "This domain does not expose enough stable public company information for evidence-backed scoring. Use a corporate, investor-relations, newsroom, or official company-information source instead.",
        }

    if host in MARKETPLACE_OR_STOREFRONT:
        return {
            "score_allowed": False,
            "source_type": "storefront / marketplace",
            "confidence": "Low",
            "reason": "The submitted domain is primarily a consumer storefront or marketplace. It is not a reliable source for scoring the company itself. Use an official corporate or investor-information domain instead.",
        }

    if not pages or total_chars < 700:
        return {
            "score_allowed": False,
            "source_type": "insufficient public access",
            "confidence": "Low",
            "reason": "Too little usable public text was accessible from this domain to calculate a defensible fit score.",
        }

    if meaningful_pages < 2 and total_chars < 1800:
        return {
            "score_allowed": False,
            "source_type": "thin public source",
            "confidence": "Low",
            "reason": "Only a thin public source was available. LeadScope saved what it could verify, but there is not enough evidence for a reliable fit score.",
        }

    if quality_status == "insufficient evidence":
        return {
            "score_allowed": False,
            "source_type": "insufficient evidence",
            "confidence": "Low",
            "reason": str(row.get("quality_reason") or "The extracted evidence did not meet the minimum threshold for a defensible fit score."),
        }

    return {
        "score_allowed": True,
        "source_type": "public company website",
        "confidence": "High" if meaningful_pages >= 3 and total_chars >= 3500 else "Medium",
        "reason": "The public source contains enough usable company information for evidence-backed scoring.",
    }
