from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any

from fastapi import HTTPException

import app_core as _core
from app_core import *  # noqa: F401,F403
from src.data_engine import company_profile as basic_company_profile
from src.data_engine import summarize_library
from src.data_engine_ext import company_profile
from src.identity_resolver import resolve_company_identity
from src.library_sources import fetch_wikidata_europe_companies
from src.storage import (
    bulk_import_seed,
    company_count,
    dashboard_stats,
    get_company,
    get_icp,
    list_companies,
)
from src.workspace_state import ensure_workspace_initialized, remove_workspace_account, set_workspace_account

ROOT = Path(__file__).resolve().parent
app = _core.app
app.version = "6.3.1"


def _read(name: str) -> str:
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


_LIBRARY_EXPAND = {"status": "idle", "target": 10000, "added": 0, "checked": 0, "message": ""}
_LIBRARY_EXPAND_LOCK = threading.Lock()


def _library_expand_worker(target: int = 10000) -> None:
    target = max(1000, min(int(target), 10000))
    with _LIBRARY_EXPAND_LOCK:
        _LIBRARY_EXPAND.update(status="running", target=target, message="Indexing public European companies…")
    offset = 0
    batch_size = 250
    total_added = 0
    try:
        while company_count() < target and offset < 30000:
            items = fetch_wikidata_europe_companies(limit=batch_size, offset=offset)
            if not items:
                break
            result = bulk_import_seed(
                items,
                limit=max(0, target - company_count()),
                source_name="Wikidata · European businesses with official websites",
            )
            total_added += int(result.get("added") or 0)
            offset += batch_size
            with _LIBRARY_EXPAND_LOCK:
                _LIBRARY_EXPAND.update(
                    added=total_added,
                    checked=offset,
                    message=f"{company_count()} companies indexed · checking public source batch {offset // batch_size}",
                )
            time.sleep(0.8)
        with _LIBRARY_EXPAND_LOCK:
            _LIBRARY_EXPAND.update(
                status="done",
                added=total_added,
                checked=offset,
                message=f"Library now contains {company_count()} companies",
            )
    except Exception as exc:
        with _LIBRARY_EXPAND_LOCK:
            _LIBRARY_EXPAND.update(
                status="error",
                added=total_added,
                checked=offset,
                message=f"Library expansion paused: {type(exc).__name__}: {str(exc)[:240]}",
            )


@app.post("/api/library/expand")
def api_library_expand(target: int = 10000):
    target = max(1000, min(int(target), 10000))
    with _LIBRARY_EXPAND_LOCK:
        if _LIBRARY_EXPAND.get("status") in {"running", "starting"}:
            return dict(_LIBRARY_EXPAND)
        _LIBRARY_EXPAND.update(
            status="starting",
            target=target,
            added=0,
            checked=0,
            message="Starting public company indexing…",
        )
    threading.Thread(target=_library_expand_worker, args=(target,), daemon=True, name="library-expand").start()
    return {"status": "starting", "target": target}


@app.get("/api/library/expand/status")
def api_library_expand_status():
    with _LIBRARY_EXPAND_LOCK:
        return dict(_LIBRARY_EXPAND) | {"company_count": company_count()}


def _filter_profiles(profiles: list[dict[str, Any]], level: str, decision: str, audience: str) -> list[dict[str, Any]]:
    if level:
        profiles = [x for x in profiles if str(x.get("data_level") or "").lower() == level.lower()]
    if decision:
        profiles = [x for x in profiles if str((x.get("decision") or {}).get("decision") or "").lower() == decision.lower()]
    if audience:
        profiles = [x for x in profiles if audience.lower() in str(x.get("audience") or "").lower()]
    return profiles


def _sort_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decision_rank = {"CONTACT": 0, "MONITOR": 1, "REVIEW": 2, "RESEARCH": 3, "SOURCE NEEDED": 4, "SKIP": 5}
    profiles.sort(key=lambda x: (
        decision_rank.get(str((x.get("decision") or {}).get("decision") or ""), 9),
        -int(((x.get("decision") or {}).get("priority") or 0)),
        -int(x.get("completeness") or 0),
        str(x.get("company") or "").lower(),
    ))
    return profiles


@app.get("/api/library")
def api_library(q: str = "", level: str = "", decision: str = "", audience: str = "", limit: int = 200, offset: int = 0):
    """Fast, paged Company Library.

    Important: this endpoint never enriches the whole database synchronously. Advanced
    filters scan a bounded window; normal browsing only profiles the requested page.
    """
    limit = max(1, min(int(limit), 250))
    offset = max(0, int(offset))
    has_advanced_filter = bool(level or decision or audience)
    scan_limit = min(1200, max(limit * 4, 300)) if has_advanced_filter else limit
    scan_offset = 0 if has_advanced_filter else offset
    rows = list_companies(q=q, limit=scan_limit, offset=scan_offset)
    icp = get_icp()
    profiles = [basic_company_profile(row, icp) for row in rows]
    profiles = _filter_profiles(profiles, level, decision, audience)
    profiles = _sort_profiles(profiles)
    if has_advanced_filter:
        profiles = profiles[offset:offset + limit]

    sample_summary = summarize_library(profiles)
    db_stats = dashboard_stats()
    summary = {
        **sample_summary,
        "total": int(db_stats.get("total") or company_count()),
        "researched": int(db_stats.get("researched") or 0),
        "scope": "page",
    }
    return {"items": profiles[:limit], "count": len(profiles), "summary": summary}


@app.get("/api/data-engine/stats")
def api_data_engine_stats():
    """Lightweight library stats; no full-database profile loop."""
    db_stats = dashboard_stats()
    sample_rows = list_companies(limit=250, offset=0)
    icp = get_icp()
    sample = [basic_company_profile(row, icp) for row in sample_rows]
    summary = summarize_library(sample)
    summary.update({
        "total": int(db_stats.get("total") or 0),
        "researched": int(db_stats.get("researched") or 0),
        "sample_size": len(sample),
    })
    return summary


@app.get("/api/workspace-v2")
def api_workspace_v2():
    """Return only real workspace accounts. Never scan the Company Library here."""
    state = ensure_workspace_initialized()
    icp = get_icp()
    accounts: list[dict[str, Any]] = []
    for key, meta in state.items():
        if str(meta.get("state") or "active") == "archived":
            continue
        row = get_company(int(key))
        if not row:
            continue
        profile = company_profile(row, icp)
        profile["workspace_state"] = meta
        accounts.append(profile)

    def priority_value(item: dict[str, Any]) -> int:
        return int(((item.get("decision") or {}).get("priority") or 0))

    accounts.sort(key=lambda x: (-priority_value(x), str(x.get("company") or "").lower()))
    contact = [
        x for x in accounts
        if (x.get("decision") or {}).get("decision") == "CONTACT"
        and (x.get("workspace_state") or {}).get("state") != "monitor"
    ]
    monitor = [
        x for x in accounts
        if (x.get("decision") or {}).get("decision") == "MONITOR"
        or (x.get("workspace_state") or {}).get("state") == "monitor"
    ]
    queue = [
        x for x in accounts
        if (x.get("workspace_state") or {}).get("state") == "queue"
        or x.get("data_level") != "Researched"
        or (x.get("decision") or {}).get("decision") in {"RESEARCH", "SOURCE NEEDED"}
    ]
    source_issues = [x for x in accounts if (x.get("decision") or {}).get("decision") == "SOURCE NEEDED"]
    changes_count = sum(int(x.get("changes_count") or 0) for x in accounts)

    return {
        "counts": {
            "accounts": len(accounts),
            "contact": len(contact),
            "monitor": len(monitor),
            "research_queue": len(queue),
            "source_issues": len(source_issues),
            "changes": changes_count,
        },
        "accounts": accounts,
        "contact": contact,
        "monitor": monitor,
        "research_queue": queue,
        "source_issues": source_issues,
    }


@app.get("/api/workspace-v2/suggestions")
def api_workspace_suggestions(limit: int = 6):
    """Small independent recommendation query so Today can render immediately."""
    limit = max(1, min(int(limit), 12))
    state = ensure_workspace_initialized()
    member_ids = {int(k) for k in state.keys()}
    icp = get_icp()
    # A bounded sample is deliberate: suggestions must never block the workspace.
    rows = list_companies(limit=400, offset=0)
    profiles = [basic_company_profile(row, icp) for row in rows if int(row.get("id") or 0) not in member_ids]
    profiles = [
        x for x in profiles
        if x.get("data_level") != "Researched"
        and (x.get("source") or {}).get("status") != "Needs better source"
    ]
    profiles.sort(key=lambda x: (
        -int((x.get("icp_prefilter") or {}).get("score") or 0),
        -int(x.get("completeness") or 0),
    ))
    return {"items": profiles[:limit]}


@app.post("/api/workspace-v2/accounts/{company_id}")
def api_workspace_add(company_id: int, payload: dict[str, Any]):
    if not get_company(company_id):
        raise HTTPException(404, "Company not found")
    state = str(payload.get("state") or "active")
    meta = set_workspace_account(company_id, state=state, source="user")
    return {"ok": True, "company_id": company_id, "workspace_state": meta}


@app.delete("/api/workspace-v2/accounts/{company_id}")
def api_workspace_remove(company_id: int):
    return {"ok": remove_workspace_account(company_id), "company_id": company_id}


@app.get("/api/companies/{company_id}/identity")
def api_company_identity(company_id: int):
    row = get_company(company_id)
    if not row:
        raise HTTPException(404, "Company not found")
    try:
        return resolve_company_identity(str(row.get("company") or ""), str(row.get("website") or ""))
    except Exception as exc:
        raise HTTPException(502, f"Public identity lookup unavailable: {type(exc).__name__}: {str(exc)[:220]}") from exc


@app.get("/api/companies/{company_id}/intelligence")
def api_company_intelligence(company_id: int):
    row = get_company(company_id)
    if not row:
        raise HTTPException(404, "Company not found")
    return company_profile(row, get_icp())


_extra_css = "\n".join([
    _read("workspace_loader_v56.css"),
    _read("source_quality_v57.css"),
    _read("data_engine_v60.css"),
    _read("workspace_v61.css"),
    _read("changes_v62.css"),
    _read("identity_v63.css"),
])
_extra_js = "\n".join([
    _read("workspace_loader_v56.js"),
    _read("source_quality_v57.js"),
    _read("data_engine_v60.js"),
    _read("workspace_v61.js"),
    _read("changes_v62.js"),
    _read("identity_v63.js"),
])

_core.HTML = _core.HTML.replace("</style>", _extra_css + "\n</style>").replace(
    "</body>", f"<script>{_extra_js}</script>\n</body>"
)
HTML = _core.HTML
