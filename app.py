from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any

from fastapi import HTTPException

import app_core as _core
from app_core import *  # noqa: F401,F403
from src.data_engine import company_profile, summarize_library
from src.library_sources import fetch_wikidata_europe_companies
from src.storage import bulk_import_seed, company_count, get_company, get_icp, list_companies
from src.workspace_state import ensure_workspace_initialized, remove_workspace_account, set_workspace_account

ROOT = Path(__file__).resolve().parent
app = _core.app
app.version = "6.0"


def _read(name: str) -> str:
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _library_rows(q: str = "", max_rows: int = 12000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while len(rows) < max_rows:
        batch = list_companies(q=q, limit=2000, offset=offset)
        rows.extend(batch)
        if len(batch) < 2000:
            break
        offset += 2000
    return rows[:max_rows]


_LIBRARY_EXPAND = {"status": "idle", "target": 10000, "added": 0, "checked": 0, "message": ""}
_LIBRARY_EXPAND_LOCK = threading.Lock()


def _library_expand_worker(target: int = 10000) -> None:
    target = max(1000, min(int(target), 10000))
    with _LIBRARY_EXPAND_LOCK:
        _LIBRARY_EXPAND.update(status="running", target=target, added=0, checked=0, message="Indexing public European companies…")
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
                _LIBRARY_EXPAND.update(added=total_added, checked=offset, message=f"{company_count()} companies indexed · checking public source batch {offset // batch_size}")
            time.sleep(0.8)
        with _LIBRARY_EXPAND_LOCK:
            _LIBRARY_EXPAND.update(status="done", added=total_added, checked=offset, message=f"Library now contains {company_count()} companies")
    except Exception as exc:
        with _LIBRARY_EXPAND_LOCK:
            _LIBRARY_EXPAND.update(status="error", added=total_added, checked=offset, message=f"Library expansion paused: {type(exc).__name__}: {str(exc)[:240]}")


@app.post("/api/library/expand")
def api_library_expand(target: int = 10000):
    with _LIBRARY_EXPAND_LOCK:
        if _LIBRARY_EXPAND.get("status") == "running":
            return dict(_LIBRARY_EXPAND)
    threading.Thread(target=_library_expand_worker, args=(target,), daemon=True, name="library-expand").start()
    return {"status": "starting", "target": max(1000, min(int(target), 10000))}


@app.get("/api/library/expand/status")
def api_library_expand_status():
    with _LIBRARY_EXPAND_LOCK:
        return dict(_LIBRARY_EXPAND) | {"company_count": company_count()}


@app.get("/api/library")
def api_library(q: str = "", level: str = "", decision: str = "", audience: str = "", limit: int = 200, offset: int = 0):
    rows = _library_rows(q=q)
    icp = get_icp()
    profiles = [company_profile(row, icp) for row in rows]
    if level:
        profiles = [x for x in profiles if str(x.get("data_level") or "").lower() == level.lower()]
    if decision:
        profiles = [x for x in profiles if str((x.get("decision") or {}).get("decision") or "").lower() == decision.lower()]
    if audience:
        profiles = [x for x in profiles if audience.lower() in str(x.get("audience") or "").lower()]

    decision_rank = {"CONTACT": 0, "MONITOR": 1, "REVIEW": 2, "RESEARCH": 3, "SOURCE NEEDED": 4, "SKIP": 5}
    profiles.sort(key=lambda x: (
        decision_rank.get(str((x.get("decision") or {}).get("decision") or ""), 9),
        -int(((x.get("decision") or {}).get("priority") or 0)),
        -int(x.get("completeness") or 0),
        str(x.get("company") or "").lower(),
    ))
    total = len(profiles)
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 500))
    return {"items": profiles[offset:offset + limit], "count": total, "summary": summarize_library(profiles)}


@app.get("/api/data-engine/stats")
def api_data_engine_stats():
    rows = _library_rows()
    icp = get_icp()
    profiles = [company_profile(row, icp) for row in rows]
    return summarize_library(profiles)


@app.get("/api/workspace-v2")
def api_workspace_v2():
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
    contact = [x for x in accounts if (x.get("decision") or {}).get("decision") == "CONTACT"]
    monitor = [x for x in accounts if (x.get("decision") or {}).get("decision") == "MONITOR" or (x.get("workspace_state") or {}).get("state") == "monitor"]
    queue = [x for x in accounts if x.get("data_level") != "Researched" or (x.get("decision") or {}).get("decision") in {"RESEARCH", "SOURCE NEEDED"}]
    source_issues = [x for x in accounts if (x.get("decision") or {}).get("decision") == "SOURCE NEEDED"]

    library_profiles = [company_profile(row, icp) for row in _library_rows(max_rows=10000)]
    member_ids = {int(k) for k in state.keys()}
    suggestions = [x for x in library_profiles if int(x.get("id") or 0) not in member_ids and x.get("data_level") != "Researched"]
    suggestions = [x for x in suggestions if (x.get("source") or {}).get("status") != "Needs better source"]
    suggestions.sort(key=lambda x: (-int((x.get("icp_prefilter") or {}).get("score") or 0), -int(x.get("completeness") or 0)))

    return {
        "counts": {
            "accounts": len(accounts),
            "contact": len(contact),
            "monitor": len(monitor),
            "research_queue": len(queue),
            "source_issues": len(source_issues),
        },
        "accounts": accounts,
        "contact": contact,
        "monitor": monitor,
        "research_queue": queue,
        "source_issues": source_issues,
        "suggestions": suggestions[:12],
    }


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
])
_extra_js = "\n".join([
    _read("workspace_loader_v56.js"),
    _read("source_quality_v57.js"),
    _read("data_engine_v60.js"),
    _read("workspace_v61.js"),
])

_core.HTML = _core.HTML.replace("</style>", _extra_css + "\n</style>").replace(
    "</body>", f"<script>{_extra_js}</script>\n</body>"
)
HTML = _core.HTML
