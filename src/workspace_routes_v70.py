from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Response

from .company_universe import universe_stats
from .storage import get_company
from .workspace_intelligence import build_workspace_intelligence
from .workspace_projects import (
    create_workspace,
    delete_workspace,
    get_workspace,
    select_company,
    select_many,
    set_workspace_result,
    unselect_company,
    update_workspace,
)
from .workspace_v7 import discover_for_workspace, workspace_company_context, workspace_detail, workspace_index

ROOT = Path(__file__).resolve().parents[1]
_BATCHES: dict[str, dict[str, Any]] = {}
_BATCH_LOCK = threading.Lock()


def _batch_snapshot(workspace_id: str) -> dict[str, Any]:
    with _BATCH_LOCK:
        return dict(_BATCHES.get(workspace_id) or {"status": "idle", "total": 0, "done": 0, "failed": 0, "current": "", "errors": []})


def register_workspace_routes(app, core) -> None:
    @app.get("/assets/workspace-v70.js")
    def workspace_v70_js():
        return Response((ROOT / "workspace_v70.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/assets/workspace-v70.css")
    def workspace_v70_css():
        return Response((ROOT / "workspace_v70.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/assets/workspace-v71.js")
    def workspace_v71_js():
        return Response((ROOT / "workspace_autocomplete_v71.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/assets/workspace-v71.css")
    def workspace_v71_css():
        return Response((ROOT / "workspace_autocomplete_v71.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/assets/workspace-v73.js")
    def workspace_v73_js():
        return Response((ROOT / "workspace_v73.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/assets/workspace-v73.css")
    def workspace_v73_css():
        return Response((ROOT / "workspace_v73.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/api/company-universe/stats")
    def api_company_universe_stats():
        return universe_stats()

    @app.get("/api/workspaces")
    def api_workspaces():
        return {"items": workspace_index()}

    @app.post("/api/workspaces", status_code=201)
    def api_workspace_create(payload: dict[str, Any]):
        if not str(payload.get("industry") or payload.get("region") or payload.get("keywords") or "").strip():
            raise HTTPException(400, "Add at least an industry, region or keyword so LeadScope knows what companies to find.")
        return create_workspace(payload)

    @app.get("/api/workspaces/{workspace_id}")
    def api_workspace_detail(workspace_id: str):
        detail = workspace_detail(workspace_id)
        if not detail:
            raise HTTPException(404, "Workspace not found")
        detail["research_batch"] = _batch_snapshot(workspace_id)
        return detail

    @app.patch("/api/workspaces/{workspace_id}")
    def api_workspace_update(workspace_id: str, payload: dict[str, Any]):
        item = update_workspace(workspace_id, payload)
        if not item:
            raise HTTPException(404, "Workspace not found")
        return item

    @app.delete("/api/workspaces/{workspace_id}")
    def api_workspace_delete(workspace_id: str):
        if not delete_workspace(workspace_id):
            raise HTTPException(404, "Workspace not found")
        return {"ok": True}

    @app.get("/api/workspaces/{workspace_id}/discover")
    def api_workspace_discover(workspace_id: str, q: str = "", limit: int = 60, page: int = 1):
        result = discover_for_workspace(workspace_id, q=q, limit=limit, page=page)
        if not result:
            raise HTTPException(404, "Workspace not found")
        return result

    @app.get("/api/workspaces/{workspace_id}/companies/{company_id}/context")
    def api_workspace_company_context(workspace_id: str, company_id: int):
        context = workspace_company_context(workspace_id, company_id)
        if not context:
            raise HTTPException(404, "Company is not selected in this workspace")
        return context

    @app.post("/api/workspaces/{workspace_id}/selected/{company_id}")
    def api_workspace_select(workspace_id: str, company_id: int):
        if not get_company(company_id):
            raise HTTPException(404, "Company not found")
        item = select_company(workspace_id, company_id)
        if not item:
            raise HTTPException(404, "Workspace not found")
        return {"ok": True, "workspace": item}

    @app.delete("/api/workspaces/{workspace_id}/selected/{company_id}")
    def api_workspace_unselect(workspace_id: str, company_id: int):
        item = unselect_company(workspace_id, company_id)
        if not item:
            raise HTTPException(404, "Workspace not found")
        return {"ok": True, "workspace": item}

    @app.post("/api/workspaces/{workspace_id}/selected")
    def api_workspace_select_many(workspace_id: str, payload: dict[str, Any]):
        ids = payload.get("company_ids") or []
        item = select_many(workspace_id, ids if isinstance(ids, list) else [])
        if not item:
            raise HTTPException(404, "Workspace not found")
        return {"ok": True, "workspace": item}

    def run_batch(workspace_id: str, company_ids: list[int], provider_name: str = "gemini") -> None:
        workspace = get_workspace(workspace_id)
        if not workspace:
            with _BATCH_LOCK:
                _BATCHES[workspace_id] = {"status": "error", "total": 0, "done": 0, "failed": 1, "current": "", "errors": [{"error": "Workspace not found"}]}
            return
        with _BATCH_LOCK:
            _BATCHES[workspace_id] = {
                "status": "running", "total": len(company_ids), "done": 0, "failed": 0,
                "current": "", "errors": [],
            }
        for company_id in company_ids:
            company = get_company(company_id)
            if not company:
                continue
            with _BATCH_LOCK:
                _BATCHES[workspace_id]["current"] = str(company.get("company") or "Company")
            try:
                # Facts are reusable across workspaces. Only crawl/extract when missing.
                if not str(company.get("quality_status") or "").strip():
                    core.analyze_company(
                        company_id,
                        fetch_live=True,
                        provider_name=provider_name,
                        progress=None,
                        generate_outreach_draft=False,
                    )
                    company = get_company(company_id) or company
                result = build_workspace_intelligence(
                    workspace,
                    company,
                    provider_name=provider_name,
                    generate_outreach=True,
                )
                set_workspace_result(workspace_id, company_id, result)
                with _BATCH_LOCK:
                    _BATCHES[workspace_id]["done"] += 1
            except Exception as exc:
                with _BATCH_LOCK:
                    _BATCHES[workspace_id]["failed"] += 1
                    errors = list(_BATCHES[workspace_id].get("errors") or [])
                    errors.append({"company_id": company_id, "company": company.get("company") or "", "error": str(exc)[:220]})
                    _BATCHES[workspace_id]["errors"] = errors[-8:]
        with _BATCH_LOCK:
            _BATCHES[workspace_id]["status"] = "done"
            _BATCHES[workspace_id]["current"] = ""

    @app.post("/api/workspaces/{workspace_id}/research", status_code=202)
    def api_workspace_research(workspace_id: str, payload: dict[str, Any] | None = None):
        detail = workspace_detail(workspace_id)
        if not detail:
            raise HTTPException(404, "Workspace not found")
        with _BATCH_LOCK:
            current = _BATCHES.get(workspace_id) or {}
            if current.get("status") == "running":
                return dict(current)

        requested = (payload or {}).get("company_ids") or []
        requested_ids = {int(x) for x in requested if str(x).isdigit()} if isinstance(requested, list) else set()
        provider_name = str((payload or {}).get("provider") or "gemini")
        candidates = detail.get("selected") or []
        ids: list[int] = []
        for profile in candidates:
            cid = int(profile.get("id") or 0)
            if requested_ids and cid not in requested_ids:
                continue
            decision = str((profile.get("decision") or {}).get("decision") or "")
            if decision == "SOURCE NEEDED":
                continue
            if decision == "RESEARCH" and cid > 0:
                ids.append(cid)
        if not ids:
            return {"status": "idle", "total": 0, "done": 0, "failed": 0, "current": "", "message": "No selected companies are waiting for workspace research."}
        thread = threading.Thread(target=run_batch, args=(workspace_id, ids, provider_name), daemon=True, name=f"workspace-research-{workspace_id}")
        thread.start()
        return {"status": "running", "total": len(ids), "done": 0, "failed": 0, "current": ""}

    @app.get("/api/workspaces/{workspace_id}/research/status")
    def api_workspace_research_status(workspace_id: str):
        if not get_workspace(workspace_id):
            raise HTTPException(404, "Workspace not found")
        return _batch_snapshot(workspace_id)
