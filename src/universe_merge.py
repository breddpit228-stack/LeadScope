from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .storage import DB_PATH, normalize_website

TAXONOMY: list[tuple[str, tuple[str, ...]]] = [
    ("Fintech", ("fintech", "financial technology", "payments", "payment processing", "banking software", "accounting software", "payroll", "insurtech", "wealthtech", "regtech")),
    ("Software & SaaS", ("software as a service", "saas", "enterprise software", "business software", "cloud software", "software company", "software platform")),
    ("AI & Data", ("artificial intelligence", "machine learning", "data platform", "data analytics", "analytics software", "computer vision", "generative ai")),
    ("Cybersecurity", ("cybersecurity", "cyber security", "information security", "network security", "identity security", "fraud prevention")),
    ("Marketing & AdTech", ("marketing technology", "martech", "advertising technology", "adtech", "digital marketing", "marketing software")),
    ("Sales & RevOps", ("sales software", "sales automation", "crm", "revenue operations", "revops", "sales enablement")),
    ("HR & Recruiting", ("human resources", "hr software", "recruiting", "recruitment", "talent management", "workforce management")),
    ("E-commerce & Retail", ("e-commerce", "ecommerce", "retail technology", "retail software", "online retail")),
    ("Marketplaces", ("marketplace", "online marketplace", "two-sided marketplace")),
    ("Logistics & Supply Chain", ("logistics", "supply chain", "freight", "shipping software", "warehouse management", "last mile")),
    ("Climate & Energy", ("climate tech", "climate technology", "renewable energy", "energy software", "solar energy", "carbon management")),
    ("Health & Life Sciences", ("healthtech", "health technology", "healthcare software", "biotechnology", "biotech", "medical technology", "digital health")),
    ("Professional Services", ("consulting", "consultancy", "software development house", "development agency", "professional services", "advisory services")),
    ("Manufacturing", ("manufacturing", "industrial automation", "factory automation", "industrial technology")),
    ("Real Estate & PropTech", ("proptech", "property technology", "real estate technology", "real estate software")),
    ("Education & EdTech", ("edtech", "education technology", "learning platform", "education software")),
    ("Telecom", ("telecommunications", "telecom", "mobile network", "communications technology")),
    ("Travel & Hospitality", ("travel technology", "travel software", "hospitality technology", "hotel software", "tourism")),
]

_GENERIC_DESCRIPTIONS = (
    "company indexed from wikidata",
    "indexed from wikidata with an official website",
    "official website:",
)


def canonical_category(values: list[str] | tuple[str, ...] | str) -> str:
    if isinstance(values, str):
        text = values.lower()
    else:
        text = " ".join(str(x or "") for x in values).lower()
    padded = f" {text} "
    for label, terms in TAXONOMY:
        if any(term in padded for term in terms):
            return label
    return ""


def _parse_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    try:
        parsed = json.loads(str(value or "[]"))
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    return []


def _merge_unique(left: list[str], right: list[str], limit: int = 16) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in [*left, *right]:
        clean = str(item or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _meaningful_description(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 24:
        return False
    low = text.lower()
    return not any(marker in low for marker in _GENERIC_DESCRIPTIONS)


def _merge_sources(existing: str, source_name: str) -> str:
    parts = [p.strip() for p in str(existing or "").split(" | ") if p.strip()]
    if source_name and source_name not in parts:
        parts.append(source_name)
    return " | ".join(parts[:4])


def merge_company_items(items: list[dict[str, Any]], limit: int = 1000, source_name: str = "Public company source") -> dict[str, int]:
    """Insert new Universe records and enrich existing domains without overwriting research.

    Deep-research fields are intentionally untouched. The merge only fills/strengthens the
    basic Discover layer: country, city, public description, employee count, category/tags,
    source URL and source provenance.
    """
    added = 0
    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    limit = max(0, int(limit))

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id,company,website,country,city,segment,team_size_public,public_signals,source_url,seed_source,seed_tags_json,quality_status FROM companies WHERE website<>''").fetchall()
        by_domain = {normalize_website(str(r["website"] or "")): dict(r) for r in rows if normalize_website(str(r["website"] or ""))}
        seen_batch: set[str] = set()

        for item in items:
            website = normalize_website(str(item.get("website") or ""))
            name = str(item.get("name") or item.get("company") or "").strip()
            if not website or not name or website in seen_batch:
                skipped += 1
                continue
            seen_batch.add(website)

            tags = item.get("tags") or []
            if isinstance(tags, str):
                tags = [x.strip() for x in tags.split(",") if x.strip()]
            tags = [str(x).strip() for x in tags if str(x).strip()]
            extra = item.get("extra") or {}
            country = str(extra.get("country") or item.get("country") or "").strip()
            city = str(extra.get("city") or item.get("city") or "").strip()
            employees = str(extra.get("team_size_public") or item.get("team_size_public") or "").strip()
            description = str(item.get("description") or "").strip()
            source_url = str(item.get("source_url") or extra.get("wikidata_url") or website).strip()
            category = canonical_category([*tags, description])
            if category and category.lower() not in {t.lower() for t in tags}:
                tags.insert(0, category)

            existing = by_domain.get(website)
            if existing:
                changes: dict[str, Any] = {}
                if not str(existing.get("country") or "").strip() and country:
                    changes["country"] = country
                if not str(existing.get("city") or "").strip() and city:
                    changes["city"] = city
                if not str(existing.get("team_size_public") or "").strip() and employees:
                    changes["team_size_public"] = employees
                current_description = str(existing.get("public_signals") or "").strip()
                if _meaningful_description(description) and not _meaningful_description(current_description):
                    changes["public_signals"] = description
                current_segment = str(existing.get("segment") or "").strip()
                if category and (not current_segment or current_segment.lower() in {"technology", "software", "company", "startup"}):
                    changes["segment"] = category
                merged_tags = _merge_unique(_parse_tags(existing.get("seed_tags_json")), tags)
                if merged_tags != _parse_tags(existing.get("seed_tags_json")):
                    changes["seed_tags_json"] = json.dumps(merged_tags, ensure_ascii=False)
                merged_source = _merge_sources(str(existing.get("seed_source") or ""), source_name)
                if merged_source != str(existing.get("seed_source") or ""):
                    changes["seed_source"] = merged_source
                if not str(existing.get("source_url") or "").strip() and source_url:
                    changes["source_url"] = source_url
                if changes:
                    changes["updated_at"] = now
                    assignments = ",".join(f"{key}=?" for key in changes)
                    conn.execute(f"UPDATE companies SET {assignments} WHERE id=?", [*changes.values(), int(existing["id"])])
                    updated += 1
                else:
                    skipped += 1
                continue

            if added >= limit:
                skipped += 1
                continue
            conn.execute('''INSERT INTO companies
                (company,website,country,city,segment,team_size_public,public_signals,source_url,seed_source,seed_tags_json,data_origin,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                name, website, country, city, category or ", ".join(tags[:6]), employees,
                description, source_url, source_name, json.dumps(tags[:16], ensure_ascii=False),
                "public_seed", now, now,
            ))
            added += 1
            by_domain[website] = {"id": int(conn.execute("SELECT last_insert_rowid()").fetchone()[0]), "website": website}
        conn.commit()
    finally:
        conn.close()

    return {"added": added, "updated": updated, "skipped": skipped}
