from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .storage import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _key(company_id: int, suffix: str) -> str:
    return f"company_snapshot:{int(company_id)}:{suffix}"


def _read(key: str, default: Any) -> Any:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return default


def _write(key: str, value: Any) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = json.dumps(value, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (key, payload, now),
        )


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _strings(value: Any) -> list[str]:
    out: list[str] = []
    for item in _list(value):
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("fact") or item.get("title") or item.get("name") or "").strip()
        else:
            text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _signal_records(value: Any) -> list[dict[str, Any]]:
    return [x for x in _list(value) if isinstance(x, dict) and str(x.get("fact") or "").strip()]


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return default


def make_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "research_score": _number(row.get("research_score")),
        "quality_status": str(row.get("quality_status") or ""),
        "services": _strings(row.get("services_json")),
        "target_roles": _strings(row.get("target_roles_json")),
        "commercial_signals": _signal_records(row.get("commercial_signals_json")),
        "proof_points": _signal_records(row.get("proof_points_json")),
    }


def compare_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    if not previous:
        return []
    changes: list[dict[str, Any]] = []

    old_signals = {str(x.get("fact") or "").strip().lower() for x in previous.get("commercial_signals", []) if isinstance(x, dict)}
    for signal in current.get("commercial_signals", []):
        if not isinstance(signal, dict):
            continue
        fact = str(signal.get("fact") or "").strip()
        if fact and fact.lower() not in old_signals:
            changes.append({
                "type": "new_signal",
                "label": "New signal",
                "title": fact,
                "date": str(signal.get("observed_date") or current.get("captured_at") or ""),
                "source_url": str(signal.get("source_url") or ""),
                "importance": _number(signal.get("signal_value")),
            })

    old_services = {x.lower() for x in previous.get("services", []) if isinstance(x, str)}
    for item in current.get("services", []):
        if isinstance(item, str) and item.lower() not in old_services:
            changes.append({
                "type": "new_product",
                "label": "New product / service",
                "title": item,
                "date": str(current.get("captured_at") or ""),
                "importance": 55,
            })

    old_roles = {x.lower() for x in previous.get("target_roles", []) if isinstance(x, str)}
    for item in current.get("target_roles", []):
        if isinstance(item, str) and item.lower() not in old_roles:
            changes.append({
                "type": "new_role",
                "label": "New buyer role",
                "title": item,
                "date": str(current.get("captured_at") or ""),
                "importance": 35,
            })

    old_score = _number(previous.get("research_score"))
    new_score = _number(current.get("research_score"))
    delta = new_score - old_score
    if abs(delta) >= 5:
        changes.append({
            "type": "fit_change",
            "label": "Fit score changed",
            "title": f"Fit moved from {old_score} to {new_score} ({delta:+d}).",
            "date": str(current.get("captured_at") or ""),
            "importance": min(80, 40 + abs(delta)),
        })

    changes.sort(key=lambda x: _number(x.get("importance")), reverse=True)
    return changes[:20]


def record_snapshot(company_id: int, row: dict[str, Any]) -> list[dict[str, Any]]:
    current = make_snapshot(row)
    previous = _read(_key(company_id, "current"), {})
    changes = compare_snapshots(previous, current)
    if previous:
        _write(_key(company_id, "previous"), previous)
    _write(_key(company_id, "current"), current)
    _write(_key(company_id, "changes"), changes)
    return changes


def get_last_changes(company_id: int) -> list[dict[str, Any]]:
    value = _read(_key(company_id, "changes"), [])
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []
