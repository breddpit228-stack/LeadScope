from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .library_sources import EUROPE_WIKIDATA_COUNTRIES, fetch_wikidata_country_batch
from .storage import bulk_import_seed, company_count

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "company_universe_index_state.json"
STATE_VERSION = 2


def _default_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "phase": "direct",
        "country_index": 0,
        "offset": 0,
        "checked": 0,
        "added": 0,
        "updated": 0,
        "completed": False,
        "last_error": "",
        "updated_at": "",
    }


def load_index_state() -> dict[str, Any]:
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and int(raw.get("version") or 0) == STATE_VERSION:
            return {**_default_state(), **raw}
    except Exception:
        pass
    return _default_state()


def save_index_state(state: dict[str, Any]) -> dict[str, Any]:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean = {**_default_state(), **state}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)
    return clean


def reset_index_state() -> dict[str, Any]:
    state = _default_state()
    save_index_state(state)
    return state


def index_status() -> dict[str, Any]:
    state = load_index_state()
    idx = max(0, min(int(state.get("country_index") or 0), len(EUROPE_WIKIDATA_COUNTRIES) - 1))
    country = EUROPE_WIKIDATA_COUNTRIES[idx][0] if EUROPE_WIKIDATA_COUNTRIES else ""
    return {**state, "country": country, "company_count": company_count()}


def _advance_country(state: dict[str, Any]) -> dict[str, Any]:
    state["country_index"] = int(state.get("country_index") or 0) + 1
    state["offset"] = 0
    if state["country_index"] >= len(EUROPE_WIKIDATA_COUNTRIES):
        if state.get("phase") == "direct":
            state["phase"] = "subclasses"
            state["country_index"] = 0
        else:
            state["completed"] = True
    return state


def index_next_batch(target: int = 10000, batch_size: int = 150) -> dict[str, Any]:
    target = max(1000, min(int(target), 50000))
    batch_size = max(50, min(int(batch_size), 250))
    state = load_index_state()
    if company_count() >= target:
        state["completed"] = True
        save_index_state(state)
        return {"state": index_status(), "result": {"added": 0, "updated": 0, "skipped": 0}}
    if state.get("completed"):
        return {"state": index_status(), "result": {"added": 0, "updated": 0, "skipped": 0}}

    if int(state.get("country_index") or 0) >= len(EUROPE_WIKIDATA_COUNTRIES):
        state = _advance_country(state)
        save_index_state(state)
        if state.get("completed"):
            return {"state": index_status(), "result": {"added": 0, "updated": 0, "skipped": 0}}

    country_name, country_qid = EUROPE_WIKIDATA_COUNTRIES[int(state.get("country_index") or 0)]
    offset = max(0, int(state.get("offset") or 0))
    include_subclasses = state.get("phase") == "subclasses"

    try:
        batch = fetch_wikidata_country_batch(
            country_qid=country_qid,
            country_name=country_name,
            limit=batch_size,
            offset=offset,
            include_subclasses=include_subclasses,
        )
        items = list(batch.get("items") or [])
        raw_count = int(batch.get("raw_count") or 0)
        result = bulk_import_seed(
            items,
            limit=max(0, target - company_count()),
            source_name=f"Wikidata · {country_name}",
        )
        state["checked"] = int(state.get("checked") or 0) + raw_count
        state["added"] = int(state.get("added") or 0) + int(result.get("added") or 0)
        state["updated"] = int(state.get("updated") or 0) + int(result.get("updated") or 0)
        state["last_error"] = ""
        state["offset"] = offset + batch_size
        if raw_count == 0 or offset >= 12000:
            state = _advance_country(state)
        save_index_state(state)
        return {"state": index_status(), "result": result, "country": country_name}
    except Exception as exc:
        state["last_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        save_index_state(state)
        raise
