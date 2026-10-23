from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .storage import DB_PATH

WORKSPACE_KEY = "workspace_v2_accounts"
INIT_KEY = "workspace_v2_initialized"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _read_setting(key: str, default: Any) -> Any:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return default


def _write_setting(key: str, value: Any) -> None:
    now = _now()
    payload = json.dumps(value, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, payload, now),
        )


def ensure_workspace_initialized() -> dict[str, dict[str, Any]]:
    initialized = bool(_read_setting(INIT_KEY, False))
    state = get_workspace_accounts(raw=True)
    if initialized:
        return state

    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, quality_status, data_origin, human_review_status, updated_at
               FROM companies
               WHERE quality_status<>'' OR data_origin='manual' OR human_review_status IN ('Reviewed','Contacted')
               ORDER BY updated_at DESC LIMIT 60"""
        ).fetchall()
    for row in rows:
        cid = str(int(row["id"]))
        state[cid] = {
            "state": "active",
            "added_at": row["updated_at"] or _now(),
            "source": "migration",
        }
    _write_setting(WORKSPACE_KEY, state)
    _write_setting(INIT_KEY, True)
    return state


def get_workspace_accounts(raw: bool = False) -> dict[str, dict[str, Any]]:
    value = _read_setting(WORKSPACE_KEY, {})
    if not isinstance(value, dict):
        value = {}
    clean: dict[str, dict[str, Any]] = {}
    for key, meta in value.items():
        try:
            cid = str(int(key))
        except Exception:
            continue
        if isinstance(meta, dict):
            clean[cid] = dict(meta)
        else:
            clean[cid] = {"state": "active", "added_at": "", "source": "legacy"}
    if raw:
        return clean
    return clean


def set_workspace_account(company_id: int, state: str = "active", source: str = "user") -> dict[str, Any]:
    allowed = {"active", "monitor", "queue", "archived"}
    state_name = state if state in allowed else "active"
    accounts = ensure_workspace_initialized()
    key = str(int(company_id))
    existing = dict(accounts.get(key) or {})
    existing.update({
        "state": state_name,
        "added_at": existing.get("added_at") or _now(),
        "updated_at": _now(),
        "source": source,
    })
    accounts[key] = existing
    _write_setting(WORKSPACE_KEY, accounts)
    return existing


def remove_workspace_account(company_id: int) -> bool:
    accounts = ensure_workspace_initialized()
    key = str(int(company_id))
    existed = key in accounts
    accounts.pop(key, None)
    _write_setting(WORKSPACE_KEY, accounts)
    return existed


# v7 routes are registered from this already-loaded compatibility module so the
# existing app.py can keep the legacy endpoints while the new project-first
# workspace becomes the primary workflow.
def _register_workspace_v7_routes() -> None:
    try:
        import app_core as _core
        if getattr(_core.app.state, "workspace_v7_routes_registered", False):
            return
        from .workspace_routes_v70 import register_workspace_routes
        register_workspace_routes(_core.app, _core)
        _core.app.state.workspace_v7_routes_registered = True
    except Exception:
        # App startup must not fail solely because an optional workspace layer
        # could not register. CI/runtime smoke tests verify the routes explicitly.
        return


_register_workspace_v7_routes()
