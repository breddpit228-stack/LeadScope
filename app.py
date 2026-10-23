from __future__ import annotations

import csv
import io
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.llm_provider import LLMProvider
from src.seed import EUROPE_DATA_URL, fetch_europe_seed
from src.service import analyze_company, recalculate_score
from src.storage import (
    bulk_import_seed, company_count, create_company, dashboard_stats, delete_company,
    find_company_by_website, get_company, get_icp, init_db, list_activity, list_companies,
    list_unresearched, log_activity, seed_demo_activity, set_icp, update_company,
)

app = FastAPI(title="LeadScope", version="5.5")
init_db(seed=True)

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_ACTIVE_BY_COMPANY: dict[int, str] = {}

_SEED = {"status": "idle", "message": "", "added": 0, "source": EUROPE_DATA_URL}
_SEED_LOCK = threading.Lock()

_BATCH: dict[str, Any] = {
    "status": "idle", "total": 0, "done": 0, "failed": 0, "current": "",
    "started_at": None, "message": "", "stop_requested": False,
}
_BATCH_LOCK = threading.Lock()


def _json_list(value: Any) -> list[Any]:
    import json
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _workspace_overview() -> dict[str, Any]:
    rows = list_companies(limit=2000)
    total = len(rows)
    researched = [r for r in rows if str(r.get("quality_status") or "").strip()]
    recommended = [r for r in researched if int(r.get("research_score") or 0) >= 65 and r.get("human_review_status") != "Rejected"]
    ready = [r for r in researched if r.get("quality_status") == "Ready for review" and r.get("human_review_status") != "Rejected"]
    enriched = []
    strong_signal_count = 0
    opportunity_count = 0
    for r in researched:
        signals = [x for x in _json_list(r.get("commercial_signals_json")) if isinstance(x, dict)]
        signals.sort(key=lambda x: int(x.get("signal_value") or 0), reverse=True)
        top_signal = signals[0] if signals else {}
        strong_signal_count += sum(1 for x in signals if int(x.get("signal_value") or 0) >= 45 and x.get("freshness") in {"current", "recent", "unknown"})
        hypotheses = [x for x in _json_list(r.get("hypotheses_json")) if isinstance(x, dict)]
        top_hyp = hypotheses[0] if hypotheses else {}
        actionable = bool(top_hyp) and int(top_signal.get("signal_value") or 0) >= 25 and int(r.get("research_score") or 0) >= 45
        if actionable and r.get("human_review_status") != "Rejected":
            opportunity_count += 1
        enriched.append({
            "id": r.get("id"), "company": r.get("company"), "website": r.get("website"),
            "country": r.get("country"), "city": r.get("city"), "segment": r.get("segment"),
            "company_summary": r.get("company_summary"), "research_score": int(r.get("research_score") or 0),
            "research_priority": r.get("research_priority"), "quality_status": r.get("quality_status"),
            "human_review_status": r.get("human_review_status"), "top_signal": top_signal,
            "top_hypothesis": top_hyp, "suggested_angle": r.get("suggested_angle"),
            "updated_at": r.get("updated_at"), "actionable": actionable,
        })
    focus = sorted(
        [x for x in enriched if x["human_review_status"] != "Rejected"],
        key=lambda x: (1 if x["actionable"] else 0, int((x.get("top_signal") or {}).get("signal_value") or 0), int(x.get("research_score") or 0)),
        reverse=True,
    )[:6]
    opportunities = sorted(
        [x for x in enriched if x["actionable"] and x["human_review_status"] != "Rejected"],
        key=lambda x: (int((x.get("top_signal") or {}).get("signal_value") or 0), int(x.get("research_score") or 0)), reverse=True
    )[:12]
    starters = [
        {
            "id": r.get("id"), "company": r.get("company"), "website": r.get("website"),
            "country": r.get("country"), "city": r.get("city"), "segment": r.get("segment"),
            "description": r.get("public_signals") or r.get("segment") or "Public company profile",
            "seed_tags_json": r.get("seed_tags_json") or "[]",
        }
        for r in rows
        if not str(r.get("quality_status") or "").strip()
        and (str(r.get("public_signals") or "").strip() or str(r.get("segment") or "").strip())
    ][:6]
    return {
        "total": total, "researched": len(researched), "needs_research": total-len(researched),
        "recommended": len(recommended), "ready": len(ready), "strong_signals": strong_signal_count,
        "opportunities": opportunity_count, "coverage_percent": round((len(researched)/total*100),1) if total else 0,
        "focus_accounts": focus, "opportunity_accounts": opportunities, "starter_accounts": starters,
    }


def _job_set(job_id: str, **changes: Any) -> None:
    with _JOBS_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(changes)


def _run_analysis_job(job_id: str, company_id: int, fetch_live: bool, provider_name: str, outreach: bool = True) -> None:
    def progress(stage: str, message: str, percent: int) -> None:
        _job_set(job_id, stage=stage, message=message, percent=max(0, min(100, int(percent))))
    try:
        result = analyze_company(company_id, fetch_live=fetch_live, provider_name=provider_name,
                                 progress=progress, generate_outreach_draft=outreach)
        _job_set(job_id, status="done", stage="done", message="Research complete.", percent=100, result_id=result.get("id"))
    except Exception as exc:
        message = str(exc)[:900]
        _job_set(job_id, status="error", stage="error", message=message, error=message, percent=100)
    finally:
        with _JOBS_LOCK:
            if _ACTIVE_BY_COMPANY.get(company_id) == job_id:
                _ACTIVE_BY_COMPANY.pop(company_id, None)


def _start_company_job(company_id: int, fetch_live: bool = True, provider: str = "gemini", outreach: bool = True) -> str:
    with _JOBS_LOCK:
        active = _ACTIVE_BY_COMPANY.get(company_id)
        if active and _JOBS.get(active, {}).get("status") == "running":
            return active
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "job_id": job_id, "company_id": company_id, "status": "running", "stage": "queued",
            "message": "Queued…", "percent": 0, "error": "", "created_at": time.time(),
        }
        _ACTIVE_BY_COMPANY[company_id] = job_id
    threading.Thread(target=_run_analysis_job, args=(job_id, company_id, fetch_live, provider, outreach),
                     daemon=True, name=f"lead-analysis-{company_id}").start()
    return job_id


def _seed_worker(force_demo_activity: bool = False) -> None:
    with _SEED_LOCK:
        _SEED.update(status="running", message="Loading 1,000 European companies…", added=0)
    try:
        data = fetch_europe_seed(timeout=35)
        target_add = max(0, 1000 - company_count())
        result = bulk_import_seed(data, limit=target_add, source_name="Open accelerator portfolios · Europe")
        demo_events = seed_demo_activity(force=force_demo_activity)
        with _SEED_LOCK:
            _SEED.update(status="done", message=f"Workspace ready · {company_count()} companies · {demo_events} demo activity events", added=result["added"])
    except Exception as exc:
        with _SEED_LOCK:
            _SEED.update(status="error", message=f"Seed import unavailable: {type(exc).__name__}: {str(exc)[:260]}")


def _batch_worker(limit: int, provider: str, delay_seconds: float) -> None:
    rows = list_unresearched(limit)
    with _BATCH_LOCK:
        _BATCH.update(status="running", total=len(rows), done=0, failed=0, current="", started_at=time.time(), message="Batch research running", stop_requested=False)
    log_activity(None, "batch_started", f"Batch research started for {len(rows)} companies", "real")
    for row in rows:
        with _BATCH_LOCK:
            if _BATCH.get("stop_requested"):
                _BATCH.update(status="stopped", message="Batch stopped by user")
                break
            _BATCH["current"] = row.get("company", "")
        try:
            analyze_company(int(row["id"]), fetch_live=True, provider_name=provider, progress=None, generate_outreach_draft=False)
            with _BATCH_LOCK:
                _BATCH["done"] += 1
        except Exception as exc:
            with _BATCH_LOCK:
                _BATCH["failed"] += 1
                _BATCH["message"] = f"Last error: {type(exc).__name__}: {str(exc)[:180]}"
            text = str(exc).lower()
            if any(x in text for x in ["429", "resource_exhausted", "503", "unavailable", "rate"]):
                time.sleep(max(30.0, delay_seconds))
        time.sleep(max(0.0, delay_seconds))
    else:
        with _BATCH_LOCK:
            _BATCH.update(status="done", current="", message="Batch research complete")
        log_activity(None, "batch_completed", f"Batch research completed · {_BATCH.get('done',0)} successful · {_BATCH.get('failed',0)} failed", "real")


class CompanyIn(BaseModel):
    company: str = Field(min_length=1, max_length=160)
    website: str = ""
    country: str = ""
    city: str = ""
    segment: str = ""
    team_size_public: str = ""
    public_signals: str = ""
    source_url: str = ""
    human_review_status: str = "New"
    notes: str = ""


class CompanyPatch(BaseModel):
    company: str | None = None
    website: str | None = None
    country: str | None = None
    city: str | None = None
    segment: str | None = None
    team_size_public: str | None = None
    human_review_status: str | None = None
    notes: str | None = None
    personalized_opener: str | None = None
    email_draft: str | None = None


class AnalyzeIn(BaseModel):
    fetch_live: bool = True
    provider: Literal["gemini", "ollama", "anthropic", "openai"] = "gemini"


class QuickResearchIn(BaseModel):
    website: str = Field(min_length=3, max_length=500)
    provider: Literal["gemini", "ollama", "anthropic", "openai"] = "gemini"


class BatchIn(BaseModel):
    limit: int = Field(default=1000, ge=1, le=1000)
    provider: Literal["gemini", "ollama", "anthropic", "openai"] = "gemini"
    delay_seconds: float = Field(default=10.0, ge=0, le=120)


@app.on_event("startup")
def _startup_seed() -> None:
    if company_count() < 1000 and os.getenv("LEADSCOPE_AUTO_SEED", "1") != "0":
        threading.Thread(target=_seed_worker, daemon=True, name="europe-seed").start()
    else:
        seed_demo_activity(force=False)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HTML


@app.get("/api/stats")
def api_stats():
    return dashboard_stats()


@app.get("/api/workspace")
def api_workspace():
    return _workspace_overview()


@app.get("/api/companies")
def api_list(q: str = "", status: str = "", priority: str = "", limit: int = 250, offset: int = 0):
    return list_companies(q=q, status=status, priority=priority, limit=limit, offset=offset)


@app.get("/api/companies/{company_id}")
def api_get(company_id: int):
    row = get_company(company_id)
    if not row:
        raise HTTPException(404, "Company not found")
    return row


@app.post("/api/companies")
def api_create(payload: CompanyIn):
    return create_company(payload.model_dump())


@app.post("/api/quick-research", status_code=202)
def api_quick_research(payload: QuickResearchIn):
    website = payload.website.strip()
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    found = find_company_by_website(website)
    if found:
        company = found
    else:
        host = urlparse(website).netloc.replace("www.", "")
        name = host.split(".")[0].replace("-", " ").title() or "New company"
        company = create_company({"company": name, "website": website, "source_url": website, "data_origin": "manual"})
    job_id = _start_company_job(int(company["id"]), fetch_live=True, provider=payload.provider, outreach=True)
    return {"job_id": job_id, "company_id": company["id"], "company": company["company"]}


@app.patch("/api/companies/{company_id}")
def api_patch(company_id: int, payload: CompanyPatch):
    row = update_company(company_id, payload.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(404, "Company not found")
    if payload.human_review_status:
        log_activity(company_id, "status_changed", f"Status changed to {payload.human_review_status}", "real")
    return row


@app.delete("/api/companies/{company_id}")
def api_delete(company_id: int):
    if not delete_company(company_id):
        raise HTTPException(404, "Company not found")
    return {"ok": True}


@app.post("/api/companies/{company_id}/analyze", status_code=202)
def api_analyze(company_id: int, payload: AnalyzeIn):
    if not get_company(company_id):
        raise HTTPException(404, "Company not found")
    job_id = _start_company_job(company_id, payload.fetch_live, payload.provider, True)
    return {"job_id": job_id, "status": "running"}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    with _JOBS_LOCK:
        job = dict(_JOBS.get(job_id) or {})
    if not job:
        raise HTTPException(404, "Analysis job not found (the app may have restarted)")
    if job.get("status") == "running" and time.time() - float(job.get("created_at") or time.time()) > 90:
        _job_set(job_id, status="error", stage="error", percent=100,
                 message="Research timed out. Saved source pages are still available.",
                 error="Research exceeded the safety limit. Retry the saved analysis.")
        with _JOBS_LOCK:
            cid = int(job.get("company_id", 0))
            if _ACTIVE_BY_COMPANY.get(cid) == job_id:
                _ACTIVE_BY_COMPANY.pop(cid, None)
            job = dict(_JOBS.get(job_id) or job)
    return job


@app.get("/api/provider/{provider_name}/status")
def api_provider_status(provider_name: str):
    if provider_name not in {"gemini", "ollama", "anthropic", "openai"}:
        raise HTTPException(404, "Unknown provider")
    provider = LLMProvider.from_env(provider_name)
    return {"provider": provider.name, "configured": provider.configured, "model": provider.model or ""}


@app.get("/api/seed/status")
def api_seed_status():
    with _SEED_LOCK:
        return dict(_SEED) | {"company_count": company_count()}


@app.post("/api/seed/europe")
def api_seed_europe():
    with _SEED_LOCK:
        if _SEED.get("status") == "running":
            return dict(_SEED)
    threading.Thread(target=_seed_worker, args=(True,), daemon=True, name="europe-seed-manual").start()
    return {"status": "running"}


@app.get("/api/activity")
def api_activity(limit: int = 100, include_demo: bool = True):
    return list_activity(limit=limit, include_demo=include_demo)


@app.get("/api/icp")
def api_icp_get():
    return get_icp()


@app.put("/api/icp")
def api_icp_put(payload: dict[str, Any]):
    saved = set_icp(payload)
    rows = list_companies(limit=2000)
    recalculated = 0
    for row in rows:
        if row.get("quality_status"):
            try:
                recalculate_score(int(row["id"]))
                recalculated += 1
            except Exception:
                continue
    return {**saved, "recalculated": recalculated}


@app.post("/api/batch/start")
def api_batch_start(payload: BatchIn):
    with _BATCH_LOCK:
        if _BATCH.get("status") == "running":
            return dict(_BATCH)
    threading.Thread(target=_batch_worker, args=(payload.limit, payload.provider, payload.delay_seconds), daemon=True, name="batch-research").start()
    return {"status": "starting"}


@app.post("/api/batch/stop")
def api_batch_stop():
    with _BATCH_LOCK:
        _BATCH["stop_requested"] = True
        return dict(_BATCH)


@app.get("/api/batch/status")
def api_batch_status():
    with _BATCH_LOCK:
        return dict(_BATCH)


@app.get("/api/export.csv")
def api_export():
    rows = list_companies(limit=2000)
    if not rows:
        content = "company\n"
    else:
        hidden = {"source_text", "source_pages_json"}
        fields = [k for k in rows[0].keys() if k not in hidden]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in fields} for r in rows)
        content = out.getvalue()
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=leadscope_export.csv"})


_BASE_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
_WORKSPACE_CSS = (ROOT / "static" / "workspace_v55.css").read_text(encoding="utf-8") if (ROOT / "static" / "workspace_v55.css").exists() else ""
_WORKSPACE_JS = (ROOT / "static" / "workspace_v55.js").read_text(encoding="utf-8") if (ROOT / "static" / "workspace_v55.js").exists() else ""
HTML = _BASE_HTML.replace("</style>", _WORKSPACE_CSS + "\n</style>").replace("</body>", f"<script>{_WORKSPACE_JS}</script>\n</body>")
