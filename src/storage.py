from __future__ import annotations

import csv
import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "lead_studio.db"
SEED_PATH = ROOT / "data" / "seed_companies.csv"

FIELDS = [
    "company", "website", "country", "city", "segment", "team_size_public",
    "public_signals", "source_url", "verified_on", "source_text", "fetch_status",
    "research_score", "research_priority", "evidence", "personalized_opener",
    "email_draft", "personalization_mode", "human_review_status", "notes",
    "company_summary", "business_type", "services_json", "target_customers_json",
    "markets_json", "target_roles_json", "proof_points_json", "verified_signals_json", "commercial_signals_json",
    "hypotheses_json", "fit_summary", "source_pages_json", "score_breakdown_json",
    "suggested_angle", "quality_status", "quality_reason", "llm_model", "analysis_error",
    "seed_source", "seed_tags_json", "data_origin"
]

NEW_COLUMNS = {
    "company_summary": "TEXT DEFAULT ''",
    "business_type": "TEXT DEFAULT ''",
    "services_json": "TEXT DEFAULT '[]'",
    "target_customers_json": "TEXT DEFAULT '[]'",
    "markets_json": "TEXT DEFAULT '[]'",
    "target_roles_json": "TEXT DEFAULT '[]'",
    "proof_points_json": "TEXT DEFAULT '[]'",
    "verified_signals_json": "TEXT DEFAULT '[]'",
    "commercial_signals_json": "TEXT DEFAULT '[]'",
    "hypotheses_json": "TEXT DEFAULT '[]'",
    "fit_summary": "TEXT DEFAULT ''",
    "source_pages_json": "TEXT DEFAULT '[]'",
    "score_breakdown_json": "TEXT DEFAULT '[]'",
    "suggested_angle": "TEXT DEFAULT ''",
    "quality_status": "TEXT DEFAULT ''",
    "quality_reason": "TEXT DEFAULT ''",
    "llm_model": "TEXT DEFAULT ''",
    "analysis_error": "TEXT DEFAULT ''",
    "seed_source": "TEXT DEFAULT ''",
    "seed_tags_json": "TEXT DEFAULT '[]'",
    "data_origin": "TEXT DEFAULT 'manual'",
}

DEFAULT_ICP = {
    "name": "Demo · European B2B Tech",
    "description": "Demo targeting profile for European B2B technology companies.",
    "offer_name": "AI workflow & lead-research automation",
    "offer_summary": "We help B2B teams automate repetitive research, qualification and outreach-preparation workflows using AI-assisted systems.",
    "value_proposition": "Reduce manual research time and give sales/marketing teams structured, review-ready account intelligence.",
    "target_roles": ["Head of Sales", "Growth Lead", "Marketing Lead", "RevOps", "Founder", "COO"],
    "desired_triggers": ["AI investment", "sales hiring", "new market expansion", "new product launch", "workflow automation", "growth hiring"],
    "geographies": ["Europe"],
    "countries": [],
    "industries": ["SaaS", "AI", "Automation", "B2B Software", "Developer Tools", "Enterprise", "Fintech", "Marketing", "Sales", "CRM"],
    "min_team_size": 10,
    "max_team_size": 250,
    "required_signals": ["B2B"],
    "preferred_signals": ["AI", "automation", "CRM", "sales", "marketing", "lead generation"],
    "disqualifiers": ["consumer only"],
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
    for name, decl in NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE companies ADD COLUMN {name} {decl}")


def init_db(seed: bool = True) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            website TEXT DEFAULT '',
            country TEXT DEFAULT '',
            city TEXT DEFAULT '',
            segment TEXT DEFAULT '',
            team_size_public TEXT DEFAULT '',
            public_signals TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            verified_on TEXT DEFAULT '',
            source_text TEXT DEFAULT '',
            fetch_status TEXT DEFAULT 'not fetched',
            research_score INTEGER DEFAULT 0,
            research_priority TEXT DEFAULT '',
            evidence TEXT DEFAULT '',
            personalized_opener TEXT DEFAULT '',
            email_draft TEXT DEFAULT '',
            personalization_mode TEXT DEFAULT '',
            human_review_status TEXT DEFAULT 'New',
            notes TEXT DEFAULT '',
            company_summary TEXT DEFAULT '',
            business_type TEXT DEFAULT '',
            services_json TEXT DEFAULT '[]',
            target_customers_json TEXT DEFAULT '[]',
            markets_json TEXT DEFAULT '[]',
            target_roles_json TEXT DEFAULT '[]',
            proof_points_json TEXT DEFAULT '[]',
            verified_signals_json TEXT DEFAULT '[]',
            commercial_signals_json TEXT DEFAULT '[]',
            hypotheses_json TEXT DEFAULT '[]',
            fit_summary TEXT DEFAULT '',
            source_pages_json TEXT DEFAULT '[]',
            score_breakdown_json TEXT DEFAULT '[]',
            suggested_angle TEXT DEFAULT '',
            quality_status TEXT DEFAULT '',
            quality_reason TEXT DEFAULT '',
            llm_model TEXT DEFAULT '',
            analysis_error TEXT DEFAULT '',
            seed_source TEXT DEFAULT '',
            seed_tags_json TEXT DEFAULT '[]',
            data_origin TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        _migrate(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_website ON companies(website)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_companies_quality ON companies(quality_status)")
        conn.execute('''CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            origin TEXT DEFAULT 'real',
            created_at TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        if conn.execute("SELECT COUNT(*) FROM settings WHERE key='icp'").fetchone()[0] == 0:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            conn.execute("INSERT INTO settings(key,value,updated_at) VALUES('icp',?,?)", (json.dumps(DEFAULT_ICP), now))
        count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if seed and count == 0 and SEED_PATH.exists():
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with SEED_PATH.open(encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    conn.execute('''INSERT INTO companies
                    (company,website,country,city,segment,team_size_public,public_signals,source_url,verified_on,data_origin,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
                        row.get("company", ""), row.get("website", ""), row.get("country", ""), row.get("city", ""),
                        row.get("segment", ""), row.get("team_size_public", ""), row.get("public_signals", ""),
                        row.get("verified_source", "") or row.get("website", ""), row.get("verified_on", ""), "legacy_seed", now, now
                    ))


def normalize_website(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    try:
        p = urlparse(value)
        host = (p.netloc or "").lower().replace("www.", "", 1)
        return f"https://{host}" if host else value.rstrip("/")
    except Exception:
        return value.rstrip("/")


def list_companies(q: str = "", status: str = "", priority: str = "", limit: int = 250, offset: int = 0) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if q:
        where.append("(company LIKE ? OR website LIKE ? OR segment LIKE ? OR company_summary LIKE ? OR public_signals LIKE ?)")
        term = f"%{q}%"
        params.extend([term] * 5)
    if status:
        where.append("human_review_status = ?")
        params.append(status)
    if priority:
        where.append("research_priority LIKE ?")
        params.append(f"{priority}%")
    sql = "SELECT * FROM companies"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE WHEN quality_status<>'' THEN 0 ELSE 1 END, research_score DESC, updated_at DESC LIMIT ? OFFSET ?"
    params.extend([max(1, min(int(limit), 2000)), max(0, int(offset))])
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def company_count() -> int:
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0])


def dashboard_stats() -> dict[str, Any]:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        researched = conn.execute("SELECT COUNT(*) FROM companies WHERE quality_status<>''").fetchone()[0]
        ready = conn.execute("SELECT COUNT(*) FROM companies WHERE quality_status='Ready for review'").fetchone()[0]
        reviewed = conn.execute("SELECT COUNT(*) FROM companies WHERE human_review_status='Reviewed'").fetchone()[0]
        contacted = conn.execute("SELECT COUNT(*) FROM companies WHERE human_review_status='Contacted'").fetchone()[0]
        return {"total": total, "researched": researched, "ready": ready, "reviewed": reviewed, "contacted": contacted}


def get_company(company_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
        return dict(row) if row else None


def find_company_by_website(website: str) -> dict[str, Any] | None:
    norm = normalize_website(website)
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM companies WHERE website<>''").fetchall()
        for r in rows:
            if normalize_website(r["website"]) == norm:
                return dict(r)
    return None


def create_company(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    values = {k: data.get(k, "") for k in FIELDS}
    for key in ["services_json", "target_customers_json", "markets_json", "target_roles_json", "proof_points_json", "verified_signals_json", "commercial_signals_json", "hypotheses_json", "source_pages_json", "score_breakdown_json", "seed_tags_json"]:
        if values.get(key, "") == "":
            values[key] = "[]"
    if values.get("website"):
        values["website"] = normalize_website(str(values["website"]))
    if not values["source_url"]:
        values["source_url"] = values["website"]
    if not values["data_origin"]:
        values["data_origin"] = "manual"
    with _connect() as conn:
        cur = conn.execute(f'''INSERT INTO companies ({','.join(FIELDS)},created_at,updated_at)
        VALUES ({','.join(['?'] * (len(FIELDS)+2))})''', [values[k] for k in FIELDS] + [now, now])
        company_id = int(cur.lastrowid)
    log_activity(company_id, "company_added", f"{values['company']} added to workspace", "real")
    return get_company(company_id)  # type: ignore[return-value]


def bulk_import_seed(items: list[dict[str, Any]], limit: int = 1000, source_name: str = "Europe accelerator dataset") -> dict[str, int]:
    added = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seen: set[str] = set()
    with _connect() as conn:
        existing = {normalize_website(r[0]) for r in conn.execute("SELECT website FROM companies WHERE website<>''").fetchall()}
        for item in items:
            if added >= limit:
                break
            website = normalize_website(str(item.get("website") or ""))
            name = str(item.get("name") or item.get("company") or "").strip()
            if not website or not name or website in existing or website in seen:
                skipped += 1
                continue
            tags = item.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            extra = item.get("extra") or {}
            country = str(extra.get("country") or item.get("country") or "").strip()
            city = str(extra.get("city") or item.get("city") or "").strip()
            description = str(item.get("description") or "").strip()
            conn.execute('''INSERT INTO companies
            (company,website,country,city,segment,public_signals,source_url,seed_source,seed_tags_json,data_origin,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
                name, website, country, city, ", ".join(tags[:8]), description, website,
                source_name, json.dumps(tags, ensure_ascii=False), "public_seed", now, now
            ))
            seen.add(website)
            existing.add(website)
            added += 1
    if added:
        log_activity(None, "seed_import", f"Imported {added} European companies into the demo workspace", "real")
    return {"added": added, "skipped": skipped}


def update_company(company_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    allowed = [k for k in FIELDS if k in data]
    if not allowed:
        return get_company(company_id)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assignments = ",".join([f"{k}=?" for k in allowed] + ["updated_at=?"])
    params = [data[k] for k in allowed] + [now, company_id]
    with _connect() as conn:
        conn.execute(f"UPDATE companies SET {assignments} WHERE id=?", params)
    return get_company(company_id)


def delete_company(company_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM companies WHERE id=?", (company_id,))
        return cur.rowcount > 0


def list_unresearched(limit: int = 1000) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM companies WHERE quality_status='' ORDER BY id LIMIT ?", (max(1, min(limit, 5000)),)).fetchall()
        return [dict(r) for r in rows]


def log_activity(company_id: int | None, event_type: str, message: str, origin: str = "real", created_at: str | None = None) -> None:
    ts = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("INSERT INTO activities(company_id,event_type,message,origin,created_at) VALUES(?,?,?,?,?)", (company_id, event_type, message, origin, ts))


def list_activity(limit: int = 100, include_demo: bool = True) -> list[dict[str, Any]]:
    where = "" if include_demo else "WHERE a.origin<>'demo_seed'"
    with _connect() as conn:
        rows = conn.execute(f'''SELECT a.*, c.company FROM activities a LEFT JOIN companies c ON c.id=a.company_id
            {where} ORDER BY a.created_at DESC LIMIT ?''', (max(1, min(limit, 1000)),)).fetchall()
        return [dict(r) for r in rows]


def seed_demo_activity(force: bool = False) -> int:
    with _connect() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM activities WHERE origin='demo_seed'").fetchone()[0]
        if existing and not force:
            return int(existing)
        if force:
            conn.execute("DELETE FROM activities WHERE origin='demo_seed'")
        companies = conn.execute("SELECT id, company FROM companies ORDER BY id LIMIT 350").fetchall()
    if not companies:
        return 0
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    events = []
    labels = [
        ("demo_review", "reviewed in demo workspace"),
        ("demo_shortlist", "added to demo shortlist"),
        ("demo_note", "received a demo review note"),
        ("demo_queue", "queued in demo research workflow"),
    ]
    for i in range(min(240, len(companies))):
        row = companies[(i * 7) % len(companies)]
        et, phrase = labels[i % len(labels)]
        dt = now - timedelta(hours=rng.randint(2, 24 * 30), minutes=rng.randint(0, 59))
        events.append((int(row["id"]), et, f"{row['company']} {phrase}", "demo_seed", dt.isoformat(timespec="seconds")))
    with _connect() as conn:
        conn.executemany("INSERT INTO activities(company_id,event_type,message,origin,created_at) VALUES(?,?,?,?,?)", events)
    return len(events)


def get_icp() -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='icp'").fetchone()
    merged = dict(DEFAULT_ICP)
    if not row:
        return merged
    try:
        value = json.loads(row[0])
        if isinstance(value, dict):
            merged.update(value)
    except Exception:
        pass
    return merged


def set_icp(value: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_ICP)
    merged.update(value or {})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("INSERT INTO settings(key,value,updated_at) VALUES('icp',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (json.dumps(merged, ensure_ascii=False), now))
    log_activity(None, "icp_updated", f"ICP updated: {merged.get('name','ICP')}", "real")
    return merged


def reset_database(seed: bool = True) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db(seed=seed)
