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


def search_universe(workspace: dict[str, Any], q: str = "", scan_limit: int = 1600) -> list[dict[str, Any]]:
    """Return a bounded candidate pool using SQLite first, before Python scoring.

    This is intentionally a retrieval layer, not a fit scorer. It keeps Discover fast
    when the local universe grows beyond the original seed dataset.
    """
    scan_limit = max(50, min(int(scan_limit), 3000))
    groups: list[str] = ["website<>''"]
    params: list[Any] = []

    region = str(workspace.get("region") or "").strip()
    if region and region.lower() not in {"europe", "eu", "european union"}:
        regions = _parts(region)
        if regions:
            groups.append("(" + " OR ".join(["country LIKE ?" for _ in regions]) + ")")
            params.extend([f"%{x}%" for x in regions])
    elif region:
        countries = sorted(EUROPE_COUNTRIES)
        groups.append("(" + " OR ".join(["country=?" for _ in countries]) + ")")
        params.extend(countries)

    industry = str(workspace.get("industry") or "").strip()
    industry_terms = _aliases(industry)
    if industry_terms:
        fields = ["segment", "business_type", "company_summary", "public_signals", "seed_tags_json"]
        clauses: list[str] = []
        for term in industry_terms:
            clauses.append("(" + " OR ".join([f"{field} LIKE ?" for field in fields]) + ")")
            params.extend([f"%{term}%"] * len(fields))
        groups.append("(" + " OR ".join(clauses) + ")")

    if q.strip():
        term = f"%{q.strip()}%"
        fields = ["company", "website", "segment", "company_summary", "public_signals", "seed_tags_json"]
        groups.append("(" + " OR ".join([f"{field} LIKE ?" for field in fields]) + ")")
        params.extend([term] * len(fields))

    sql = "SELECT * FROM companies WHERE " + " AND ".join(groups)
    sql += " ORDER BY CASE WHEN quality_status<>'' THEN 0 ELSE 1 END, updated_at DESC LIMIT ?"
    params.append(scan_limit)
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    # If taxonomy fields are still sparse, fall back to a bounded regional/general pool
    # rather than returning an empty Discover screen.
    if len(rows) < 40 and industry_terms:
        fallback_groups = ["website<>''"]
        fallback_params: list[Any] = []
        if region and region.lower() not in {"europe", "eu", "european union"}:
            regions = _parts(region)
            if regions:
                fallback_groups.append("(" + " OR ".join(["country LIKE ?" for _ in regions]) + ")")
                fallback_params.extend([f"%{x}%" for x in regions])
        if q.strip():
            term = f"%{q.strip()}%"
            fallback_groups.append("(company LIKE ? OR website LIKE ? OR segment LIKE ? OR company_summary LIKE ? OR public_signals LIKE ?)")
            fallback_params.extend([term] * 5)
        sql = "SELECT * FROM companies WHERE " + " AND ".join(fallback_groups) + " ORDER BY updated_at DESC LIMIT ?"
        fallback_params.append(min(scan_limit, 900))
        with _connect() as conn:
            fallback = [dict(r) for r in conn.execute(sql, fallback_params).fetchall()]
        seen = {int(x.get("id") or 0) for x in rows}
        rows.extend(x for x in fallback if int(x.get("id") or 0) not in seen)
    return rows[:scan_limit]


def universe_stats() -> dict[str, Any]:
    with _connect() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0])
        websites = int(conn.execute("SELECT COUNT(*) FROM companies WHERE website<>''").fetchone()[0])
        researched = int(conn.execute("SELECT COUNT(*) FROM companies WHERE quality_status<>''").fetchone()[0])
        described = int(conn.execute("SELECT COUNT(*) FROM companies WHERE company_summary<>'' OR public_signals<>''").fetchone()[0])
        countries = int(conn.execute("SELECT COUNT(DISTINCT country) FROM companies WHERE country<>''").fetchone()[0])
        source_rows = conn.execute(
            "SELECT COALESCE(NULLIF(seed_source,''), data_origin) source, COUNT(*) n FROM companies GROUP BY source ORDER BY n DESC LIMIT 12"
        ).fetchall()
    sources = [{"source": str(r[0] or "unknown"), "count": int(r[1] or 0)} for r in source_rows]
    return {
        "total": total,
        "with_website": websites,
        "with_description": described,
        "researched": researched,
        "countries": countries,
        "sources": sources,
    }
