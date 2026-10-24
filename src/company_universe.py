from __future__ import annotations

import re
import sqlite3
from typing import Any

from .storage import DB_PATH

CATEGORY_ALIASES: dict[str, list[str]] = {
    "fintech": ["fintech", "payment", "banking", "accounting", "payroll", "finance", "lending", "insurance"],
    "software & saas": ["saas", "software", "cloud", "platform", "api", "developer tools"],
    "b2b saas": ["saas", "software", "cloud", "platform", "b2b"],
    "ai & data": ["artificial intelligence", "machine learning", " ai ", "analytics", "data platform", "llm"],
    "ai / data software": ["artificial intelligence", "machine learning", " ai ", "analytics", "data platform", "llm"],
    "cybersecurity": ["cybersecurity", "security", "identity", "fraud", "risk", "compliance"],
    "marketing & adtech": ["marketing", "martech", "advertising", "adtech", "campaign", "attribution"],
    "martech": ["marketing", "martech", "advertising", "campaign", "attribution"],
    "sales & revops": ["sales", "revops", "crm", "prospecting", "revenue", "lead generation"],
    "salestech": ["sales", "revops", "crm", "prospecting", "revenue", "lead generation"],
    "hr & recruiting": ["hr", "recruit", "payroll", "workforce", "talent", "people"],
    "hr tech": ["hr", "recruit", "payroll", "workforce", "talent", "people"],
    "e-commerce & retail": ["ecommerce", "e-commerce", "retail", "commerce", "shopping"],
    "e-commerce": ["ecommerce", "e-commerce", "retail", "commerce", "shopping"],
    "marketplaces": ["marketplace", "platform", "buyers and sellers"],
    "marketplace": ["marketplace", "platform", "buyers and sellers"],
    "logistics & supply chain": ["logistics", "supply chain", "delivery", "freight", "fleet", "warehouse"],
    "logistics tech": ["logistics", "supply chain", "delivery", "freight", "fleet", "warehouse"],
    "climate & energy": ["climate", "energy", "carbon", "renewable", "solar", "sustainability"],
    "climate tech": ["climate", "energy", "carbon", "renewable", "solar", "sustainability"],
    "health & life sciences": ["health", "medical", "clinical", "biotech", "life science", "pharma"],
    "healthtech": ["health", "medical", "clinical", "biotech", "life science", "pharma"],
    "professional services": ["consulting", "agency", "advisory", "professional services"],
    "manufacturing": ["manufacturing", "industrial", "factory", "production"],
    "real estate & proptech": ["real estate", "proptech", "property", "housing"],
    "education & edtech": ["education", "edtech", "learning", "training"],
    "telecom": ["telecom", "telecommunications", "connectivity", "network"],
    "travel & hospitality": ["travel", "hotel", "hospitality", "booking", "tourism"],
}

EUROPE_COUNTRIES = {
    "Albania", "Andorra", "Austria", "Belarus", "Belgium", "Bosnia and Herzegovina", "Bulgaria",
    "Croatia", "Cyprus", "Czechia", "Czech Republic", "Denmark", "Estonia", "Finland", "France",
    "Germany", "Greece", "Hungary", "Iceland", "Ireland", "Italy", "Kosovo", "Latvia", "Liechtenstein",
    "Lithuania", "Luxembourg", "Malta", "Moldova", "Monaco", "Montenegro", "Netherlands", "North Macedonia",
    "Norway", "Poland", "Portugal", "Romania", "San Marino", "Serbia", "Slovakia", "Slovenia", "Spain",
    "Sweden", "Switzerland", "Ukraine", "United Kingdom", "UK", "Vatican City",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _parts(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;/|]+", str(value or "")) if x.strip()]


def _aliases(industry: str) -> list[str]:
    key = str(industry or "").strip().lower()
    values = list(CATEGORY_ALIASES.get(key) or [])
    if key and key not in values:
        values.insert(0, key)
    return values[:10]


def _quality_order() -> str:
    return """CASE WHEN quality_status<>'' THEN 0 ELSE 1 END,
        CASE WHEN segment<>'' OR business_type<>'' THEN 0 ELSE 1 END,
        CASE WHEN company_summary<>'' OR public_signals<>'' THEN 0 ELSE 1 END,
        CASE WHEN country<>'' THEN 0 ELSE 1 END,
        CASE WHEN team_size_public<>'' THEN 0 ELSE 1 END,
        updated_at DESC"""


def _region_filter(region: str) -> tuple[list[str], list[Any]]:
    groups: list[str] = []
    params: list[Any] = []
    if region and region.lower() not in {"europe", "eu", "european union"}:
        regions = _parts(region)
        if regions:
            groups.append("(" + " OR ".join(["country LIKE ?" for _ in regions]) + ")")
            params.extend([f"%{x}%" for x in regions])
    elif region:
        countries = sorted(EUROPE_COUNTRIES)
        groups.append("(" + " OR ".join(["country=?" for _ in countries]) + ")")
        params.extend(countries)
    return groups, params


def _query_rows(groups: list[str], params: list[Any], limit: int) -> list[dict[str, Any]]:
    sql = "SELECT * FROM companies WHERE " + " AND ".join(groups)
    sql += " ORDER BY " + _quality_order() + " LIMIT ?"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, [*params, int(limit)]).fetchall()]


def search_universe(workspace: dict[str, Any], q: str = "", scan_limit: int = 1600) -> list[dict[str, Any]]:
    """Return a broad candidate pool before Python/evidence scoring.

    Discover must not depend entirely on pre-existing taxonomy. We first retrieve
    industry-likely rows, then supplement them with a bounded regional pool so companies
    with sparse/incorrect category metadata can still be evaluated from their description.
    The strict matcher decides Strong vs Broader afterwards.
    """
    scan_limit = max(50, min(int(scan_limit), 4000))
    region = str(workspace.get("region") or "").strip()
    industry = str(workspace.get("industry") or "").strip()
    industry_terms = _aliases(industry)
    q_value = q.strip()

    base_groups = ["website<>''"]
    base_params: list[Any] = []
    region_groups, region_params = _region_filter(region)
    base_groups.extend(region_groups)
    base_params.extend(region_params)

    # User search is intentionally narrow: do not mix unrelated regional rows into a
    # named-company query.
    if q_value:
        term = f"%{q_value}%"
        fields = ["company", "website", "segment", "company_summary", "public_signals", "seed_tags_json"]
        search_groups = [*base_groups, "(" + " OR ".join([f"{field} LIKE ?" for field in fields]) + ")"]
        search_params = [*base_params, *([term] * len(fields))]
        return _query_rows(search_groups, search_params, scan_limit)

    # Keep room for regional discovery even when taxonomy already returns hundreds of
    # rows. Specific-country workspaces get a larger regional supplement because the
    # pool is naturally bounded and this is where sparse taxonomy hurts most.
    specific_region = bool(region and region.lower() not in {"europe", "eu", "european union"})
    if industry_terms:
        primary_budget = min(scan_limit, 900 if specific_region else max(700, int(scan_limit * 0.72)))
    else:
        primary_budget = scan_limit

    primary_groups = list(base_groups)
    primary_params = list(base_params)
    if industry_terms:
        fields = ["segment", "business_type", "company_summary", "public_signals", "seed_tags_json"]
        clauses: list[str] = []
        for term in industry_terms:
            clauses.append("(" + " OR ".join([f"{field} LIKE ?" for field in fields]) + ")")
            primary_params.extend([f"%{term}%"] * len(fields))
        primary_groups.append("(" + " OR ".join(clauses) + ")")

    rows = _query_rows(primary_groups, primary_params, primary_budget)

    # Always supplement industry searches with a broader regional pool. This avoids the
    # old failure mode where 40+ noisy taxonomy rows prevented fallback and hid real
    # candidates whose category field was empty or wrong.
    if industry_terms and len(rows) < scan_limit:
        supplement_budget = scan_limit - len(rows)
        if not specific_region:
            supplement_budget = min(supplement_budget, 650)
        supplement = _query_rows(base_groups, base_params, supplement_budget)
        seen = {int(x.get("id") or 0) for x in rows}
        rows.extend(x for x in supplement if int(x.get("id") or 0) not in seen)

    return rows[:scan_limit]


def universe_stats() -> dict[str, Any]:
    with _connect() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0])
        websites = int(conn.execute("SELECT COUNT(*) FROM companies WHERE website<>''").fetchone()[0])
        researched = int(conn.execute("SELECT COUNT(*) FROM companies WHERE quality_status<>''").fetchone()[0])
        described = int(conn.execute("SELECT COUNT(*) FROM companies WHERE company_summary<>'' OR public_signals<>''").fetchone()[0])
        categorized = int(conn.execute("SELECT COUNT(*) FROM companies WHERE segment<>'' OR business_type<>''").fetchone()[0])
        sized = int(conn.execute("SELECT COUNT(*) FROM companies WHERE team_size_public<>''").fetchone()[0])
        located = int(conn.execute("SELECT COUNT(*) FROM companies WHERE country<>''").fetchone()[0])
        countries = int(conn.execute("SELECT COUNT(DISTINCT country) FROM companies WHERE country<>''").fetchone()[0])
        source_rows = conn.execute(
            "SELECT COALESCE(NULLIF(seed_source,''), data_origin) source, COUNT(*) n FROM companies GROUP BY source ORDER BY n DESC LIMIT 12"
        ).fetchall()
        category_rows = conn.execute(
            "SELECT segment, COUNT(*) n FROM companies WHERE segment<>'' GROUP BY segment ORDER BY n DESC LIMIT 12"
        ).fetchall()
    sources = [{"source": str(r[0] or "unknown"), "count": int(r[1] or 0)} for r in source_rows]
    categories = [{"category": str(r[0] or "unknown"), "count": int(r[1] or 0)} for r in category_rows]

    def pct(value: int) -> int:
        return round((value / total) * 100) if total else 0

    return {
        "total": total,
        "with_website": websites,
        "with_description": described,
        "with_category": categorized,
        "with_team_size": sized,
        "with_country": located,
        "researched": researched,
        "countries": countries,
        "coverage": {
            "website": pct(websites),
            "description": pct(described),
            "category": pct(categorized),
            "team_size": pct(sized),
            "country": pct(located),
        },
        "sources": sources,
        "categories": categories,
    }
