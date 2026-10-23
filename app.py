from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

import app_core as _core
from app_core import *  # noqa: F401,F403
from src.data_engine import company_profile, summarize_library
from src.storage import get_company, get_icp, list_companies

ROOT = Path(__file__).resolve().parent
app = _core.app
app.version = "6.0"


def _read(name: str) -> str:
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


@app.get("/api/library")
def api_library(q: str = "", level: str = "", decision: str = "", audience: str = "", limit: int = 200, offset: int = 0):
    rows = list_companies(q=q, limit=2000)
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
    rows = list_companies(limit=2000)
    icp = get_icp()
    profiles = [company_profile(row, icp) for row in rows]
    return summarize_library(profiles)


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
])
_extra_js = "\n".join([
    _read("workspace_loader_v56.js"),
    _read("source_quality_v57.js"),
    _read("data_engine_v60.js"),
])

_core.HTML = _core.HTML.replace("</style>", _extra_css + "\n</style>").replace(
    "</body>", f"<script>{_extra_js}</script>\n</body>"
)
HTML = _core.HTML
