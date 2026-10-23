from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .storage import DB_PATH

WORKSPACES_KEY = "workspace_projects_v7"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _read() -> dict[str, dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (WORKSPACES_KEY,)).fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row[0])
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write(value: dict[str, dict[str, Any]]) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (WORKSPACES_KEY, payload, _now()),
        )


def _clean_ids(values: Any) -> list[int]:
    out: list[int] = []
    for value in values if isinstance(values, list) else []:
        try:
            cid = int(value)
        except Exception:
            continue
        if cid > 0 and cid not in out:
            out.append(cid)
    return out


def _clean_results(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, result in value.items():
        try:
            cid = str(int(key))
        except Exception:
            continue
        if isinstance(result, dict):
            out[cid] = dict(result)
    return out


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "Untitled workspace").strip()[:120],
        "industry": str(item.get("industry") or "").strip()[:160],
        "region": str(item.get("region") or "").strip()[:160],
        "audience": str(item.get("audience") or "Any").strip()[:40] or "Any",
        "company_size": str(item.get("company_size") or "").strip()[:80],
        "keywords": str(item.get("keywords") or "").strip()[:300],
        "offer": str(item.get("offer") or "").strip()[:600],
        "selected_ids": _clean_ids(item.get("selected_ids")),
        "company_results": _clean_results(item.get("company_results")),
        "created_at": str(item.get("created_at") or _now()),
        "updated_at": str(item.get("updated_at") or _now()),
    }


def list_workspaces() -> list[dict[str, Any]]:
    items = [_normalize(x) for x in _read().values() if isinstance(x, dict)]
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return items


def get_workspace(workspace_id: str) -> dict[str, Any] | None:
    raw = _read().get(str(workspace_id))
    return _normalize(raw) if isinstance(raw, dict) else None


def create_workspace(payload: dict[str, Any]) -> dict[str, Any]:
    store = _read()
    workspace_id = uuid.uuid4().hex[:10]
    now = _now()
    item = _normalize({**payload, "id": workspace_id, "created_at": now, "updated_at": now, "selected_ids": [], "company_results": {}})
    if not item["name"] or item["name"] == "Untitled workspace":
        industry = item.get("industry") or "Company"
        region = item.get("region") or "search"
        item["name"] = f"{industry} · {region}"[:120]
    store[workspace_id] = item
    _write(store)
    return item


def update_workspace(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    store = _read()
    current = store.get(str(workspace_id))
    if not isinstance(current, dict):
        return None
    allowed = {"name", "industry", "region", "audience", "company_size", "keywords", "offer"}
    merged = dict(current)
    targeting_changed = False
    for key in allowed:
        if key in payload:
            new_value = payload[key]
            if key != "name" and str(current.get(key) or "") != str(new_value or ""):
                targeting_changed = True
            merged[key] = new_value
    # Workspace intelligence is relative to targeting/offer. Never keep stale scores
    # after the user changes those inputs.
    if targeting_changed:
        merged["company_results"] = {}
    merged["updated_at"] = _now()
    item = _normalize(merged)
    store[str(workspace_id)] = item
    _write(store)
    return item


def delete_workspace(workspace_id: str) -> bool:
    store = _read()
    existed = str(workspace_id) in store
    store.pop(str(workspace_id), None)
    if existed:
        _write(store)
    return existed


def select_company(workspace_id: str, company_id: int) -> dict[str, Any] | None:
    store = _read()
    current = store.get(str(workspace_id))
    if not isinstance(current, dict):
        return None
    ids = _clean_ids(current.get("selected_ids"))
    cid = int(company_id)
    if cid not in ids:
        ids.append(cid)
    current = dict(current)
    current["selected_ids"] = ids
    current["updated_at"] = _now()
    store[str(workspace_id)] = current
    _write(store)
    return _normalize(current)


def unselect_company(workspace_id: str, company_id: int) -> dict[str, Any] | None:
    store = _read()
    current = store.get(str(workspace_id))
    if not isinstance(current, dict):
        return None
    cid = int(company_id)
    current = dict(current)
    current["selected_ids"] = [x for x in _clean_ids(current.get("selected_ids")) if x != cid]
    results = _clean_results(current.get("company_results"))
    results.pop(str(cid), None)
    current["company_results"] = results
    current["updated_at"] = _now()
    store[str(workspace_id)] = current
    _write(store)
    return _normalize(current)


def select_many(workspace_id: str, company_ids: list[int]) -> dict[str, Any] | None:
    store = _read()
    current = store.get(str(workspace_id))
    if not isinstance(current, dict):
        return None
    ids = _clean_ids(current.get("selected_ids"))
    for cid in _clean_ids(company_ids):
        if cid not in ids:
            ids.append(cid)
    current = dict(current)
    current["selected_ids"] = ids
    current["updated_at"] = _now()
    store[str(workspace_id)] = current
    _write(store)
    return _normalize(current)


def get_workspace_result(workspace_id: str, company_id: int) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_id)
    if not workspace:
        return None
    result = (workspace.get("company_results") or {}).get(str(int(company_id)))
    return dict(result) if isinstance(result, dict) else None


def set_workspace_result(workspace_id: str, company_id: int, result: dict[str, Any]) -> dict[str, Any] | None:
    store = _read()
    current = store.get(str(workspace_id))
    if not isinstance(current, dict):
        return None
    results = _clean_results(current.get("company_results"))
    payload = dict(result)
    payload["updated_at"] = _now()
    results[str(int(company_id))] = payload
    current = dict(current)
    current["company_results"] = results
    current["updated_at"] = _now()
    store[str(workspace_id)] = current
    _write(store)
    return dict(payload)


def clear_workspace_result(workspace_id: str, company_id: int) -> bool:
    store = _read()
    current = store.get(str(workspace_id))
    if not isinstance(current, dict):
        return False
    results = _clean_results(current.get("company_results"))
    key = str(int(company_id))
    existed = key in results
    results.pop(key, None)
    current = dict(current)
    current["company_results"] = results
    current["updated_at"] = _now()
    store[str(workspace_id)] = current
    _write(store)
    return existed
