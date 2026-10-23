from src.research import validate_facts, research_quality
from src.scoring import score_from_facts


def test_evidence_validation_rejects_untraceable_signal():
    pages = [{"url": "https://example.com/services", "text": "We build AI automation for B2B sales teams and CRM workflows. Our customer case reduced manual research by 35%.", "title": "Services", "status": "fetched:200"}]
    raw = {
        "company_summary": "Example builds B2B automation software.",
        "business_type": "B2B software company",
        "services": ["AI automation"],
        "target_customers": ["B2B sales teams"],
        "target_roles": ["Head of Sales"],
        "markets": ["Europe"],
        "proof_points": [
            {"category": "Case study", "fact": "Customer reduced manual research by 35%", "evidence": "customer case reduced manual research by 35%", "source_url": "https://example.com/services", "confidence": 0.95}
        ],
        "verified_signals": [
            {"category": "AI", "fact": "AI automation", "evidence": "AI automation for B2B sales teams", "source_url": "https://example.com/services", "confidence": 0.95},
            {"category": "Funding", "fact": "Raised $10m", "evidence": "Raised $10m", "source_url": "https://example.com/services", "confidence": 0.99},
        ],
        "commercial_signals": [],
    }
    facts = validate_facts(raw, pages)
    assert len(facts["verified_signals"]) == 1
    assert len(facts["proof_points"]) == 1
    assert facts["verified_signals"][0]["fact"] == "AI automation"


def test_scoring_is_offer_relative_and_explainable():
    row = {"country": "Germany", "team_size_public": "50"}
    facts = {
        "business_type": "B2B SaaS software company",
        "services": ["AI automation", "CRM workflow automation"],
        "target_customers": ["enterprise sales teams"],
        "target_roles": ["Head of Sales", "RevOps"],
        "markets": ["Europe", "Germany"],
        "verified_signals": [
            {"fact": "AI automation for sales", "category": "AI"},
            {"fact": "CRM workflow automation", "category": "CRM"},
        ],
        "proof_points": [{"fact": "Customer case study", "category": "Case study"}],
        "commercial_signals": [
            {"signal_type": "hiring", "fact": "Hiring for AI automation", "why_relevant": "Investment signal"}
        ],
    }
    profile = {
        "offer_summary": "AI automation for B2B sales research and CRM workflows",
        "value_proposition": "Reduce manual sales research",
        "target_roles": ["Head of Sales", "RevOps"],
        "industries": ["SaaS", "AI", "Automation"],
        "countries": ["Germany"],
        "required_signals": ["B2B"],
        "preferred_signals": ["AI", "automation", "CRM", "sales"],
        "desired_triggers": ["AI investment"],
        "min_team_size": 10,
        "max_team_size": 250,
        "disqualifiers": [],
    }
    score, breakdown = score_from_facts(row, facts, profile)
    assert 65 <= score <= 100
    assert len(breakdown) >= 8
    labels = {x["criterion"] for x in breakdown}
    assert "Commercial timing signals" in labels
    assert "Offer adjacency" in labels


def test_quality_gate_requires_evidence():
    facts = {"company_summary": "A company", "verified_signals": [], "proof_points": []}
    status, _ = research_quality(facts, [{"url": "x"}, {"url": "y"}])
    assert status == "Insufficient evidence"


def test_signal_ranking_penalizes_old_irrelevant_partnership():
    from datetime import date
    from src.research import enrich_commercial_signals
    profile = {
        "offer_summary": "AI workflow automation for B2B sales and marketing teams",
        "value_proposition": "Automate manual research and CRM workflows",
        "target_roles": ["Head of Sales", "RevOps"],
        "preferred_signals": ["AI", "automation", "sales"],
        "desired_triggers": ["AI investment", "product launch"],
    }
    signals = [
        {
            "signal_type": "partnership",
            "fact": "Partnership with Mastercard announced for fraud detection",
            "why_relevant": "Payment ecosystem integration",
            "observed_date": "2022-09-15",
        },
        {
            "signal_type": "technology_investment",
            "fact": "Company is investing in AI automation for sales workflows",
            "why_relevant": "Direct overlap with AI workflow automation",
            "observed_date": "2026-09-15",
        },
    ]
    ranked = enrich_commercial_signals(signals, profile, today=date(2026, 10, 23))
    assert ranked[0]["signal_type"] == "technology_investment"
    assert ranked[0]["strength"] == "high"
    assert ranked[0]["freshness"] == "current"
    assert ranked[0]["offer_relevance"] in {"high", "medium"}
    old = next(x for x in ranked if x["signal_type"] == "partnership")
    assert old["freshness"] == "dated"
    assert old["hypothesis_eligible"] is False
    assert old["signal_value"] < ranked[0]["signal_value"]
