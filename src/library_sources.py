from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "LeadScope/7.10 (public company-universe indexing; https://github.com/breddpit228-stack/LeadScope)"
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_CURSOR_PATH = ROOT / "data" / "company_universe_index_state.json"
_CURSOR_VERSION = 4

# Ordered roughly by expected company-data density so a fresh installation becomes useful
# quickly. Country-sharded queries are cheaper and more reliable than scanning all Europe.
EUROPE_WIKIDATA_COUNTRIES: list[tuple[str, str]] = [
    ("United Kingdom", "Q145"), ("Germany", "Q183"), ("France", "Q142"),
    ("Netherlands", "Q55"), ("Sweden", "Q34"), ("Poland", "Q36"),
    ("Denmark", "Q35"), ("Finland", "Q33"), ("Norway", "Q20"),
    ("Switzerland", "Q39"), ("Ireland", "Q27"), ("Spain", "Q29"),
    ("Italy", "Q38"), ("Belgium", "Q31"), ("Austria", "Q40"),
    ("Estonia", "Q191"), ("Portugal", "Q45"), ("Czechia", "Q213"),
    ("Lithuania", "Q37"), ("Latvia", "Q211"), ("Romania", "Q218"),
    ("Ukraine", "Q212"), ("Hungary", "Q28"), ("Greece", "Q41"),
    ("Croatia", "Q224"), ("Slovakia", "Q214"), ("Slovenia", "Q215"),
    ("Bulgaria", "Q219"), ("Serbia", "Q403"), ("Iceland", "Q189"),
    ("Luxembourg", "Q32"), ("Cyprus", "Q229"), ("Malta", "Q233"),
    ("Bosnia and Herzegovina", "Q225"), ("Albania", "Q222"),
    ("North Macedonia", "Q221"), ("Moldova", "Q217"), ("Montenegro", "Q236"),
    ("Belarus", "Q184"), ("Kosovo", "Q1246"), ("Andorra", "Q228"),
    ("Liechtenstein", "Q347"), ("Monaco", "Q235"), ("San Marino", "Q238"),
    ("Vatican City", "Q237"),
]


def _wikidata_request(query: str, timeout: int, retries: int = 2) -> dict[str, Any]:
    """Run a bounded public Wikidata query with short transient-error retries.

    The indexer is best-effort. A single slow public SPARQL shard must never make the
    whole local product appear frozen for minutes.
    """
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            response = requests.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers={
                    "Accept": "application/sparql-results+json",
                    "Accept-Encoding": "gzip, deflate",
                    "User-Agent": USER_AGENT,
                },
                timeout=max(6, int(timeout)),
            )
            if response.status_code in _TRANSIENT_STATUS:
                retry_after = response.headers.get("Retry-After")
                delay = min(6.0, float(retry_after)) if retry_after and str(retry_after).isdigit() else min(5.0, (1.5 ** attempt) + random.uniform(0.1, 0.5))
                last_error = requests.HTTPError(f"Wikidata temporary HTTP {response.status_code}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt >= retries - 1:
                break
            time.sleep(min(4.0, (1.6 ** attempt) + random.uniform(0.1, 0.4)))
    if last_error:
        raise last_error
    raise RuntimeError("Wikidata returned no usable response")


def _clean_number(value: str) -> str:
    try:
        number = int(float(str(value or "").strip()))
        return str(number) if number > 0 else ""
    except Exception:
        return ""


def fetch_wikidata_country_batch(
    country_qid: str,
    country_name: str,
    limit: int = 100,
    offset: int = 0,
    timeout: int = 12,
    include_subclasses: bool = False,
) -> dict[str, Any]:
    """Fetch one small country-sharded Wikidata company batch."""
    limit = max(1, min(int(limit), 150))
    offset = max(0, int(offset))
    qid = str(country_qid or "").strip()
    if not qid.startswith("Q") or not qid[1:].isdigit():
        raise ValueError("Invalid Wikidata country QID")

    if include_subclasses:
        kind_clause = '''
      ?company wdt:P31 ?kind .
      VALUES ?root { wd:Q4830453 wd:Q783794 }
      ?kind wdt:P279* ?root .'''
    else:
        kind_clause = '''
      VALUES ?kind { wd:Q4830453 wd:Q783794 }
      ?company wdt:P31 ?kind .'''

    query = f'''SELECT DISTINCT ?company ?companyLabel ?companyDescription ?website ?industryLabel ?employees WHERE {{
      {kind_clause}
      ?company wdt:P856 ?website ;
               wdt:P17 wd:{qid} .
      OPTIONAL {{ ?company wdt:P452 ?industry . }}
      OPTIONAL {{ ?company wdt:P1128 ?employees . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT {limit}
    OFFSET {offset}'''

    payload = _wikidata_request(query, timeout=timeout, retries=2)
    bindings = payload.get("results", {}).get("bindings", [])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in bindings:
        name = str((row.get("companyLabel") or {}).get("value") or "").strip()
        website = str((row.get("website") or {}).get("value") or "").strip()
        industry = str((row.get("industryLabel") or {}).get("value") or "").strip()
        wikidata_description = str((row.get("companyDescription") or {}).get("value") or "").strip()
        employees = _clean_number((row.get("employees") or {}).get("value") or "")
        item_url = str((row.get("company") or {}).get("value") or "").strip()
        if not name or not website or website in seen:
            continue
        seen.add(website)
        tags = [x for x in [industry, "Wikidata"] if x]
        description = wikidata_description or (f"{country_name} company indexed from Wikidata · industry: {industry}." if industry else f"{country_name} company indexed from Wikidata with an official website.")
        out.append({
            "name": name,
            "website": website,
            "description": description,
            "tags": tags,
            "source_url": item_url,
            "extra": {
                "country": country_name,
                "city": "",
                "wikidata_url": item_url,
                "team_size_public": employees,
            },
        })
    return {"items": out, "raw_count": len(bindings), "country": country_name, "offset": offset}


def fetch_wikidata_country_companies(
    country_qid: str,
    country_name: str,
    limit: int = 100,
    offset: int = 0,
    timeout: int = 12,
    include_subclasses: bool = False,
) -> list[dict[str, Any]]:
    return list(fetch_wikidata_country_batch(country_qid, country_name, limit, offset, timeout, include_subclasses).get("items") or [])


def _default_cursor() -> dict[str, Any]:
    return {
        "version": _CURSOR_VERSION,
        "phase": "direct",
        "country_index": 0,
        "offset": 0,
        "checked": 0,
        "complete": False,
        "skipped_shards": [],
        "last_error": "",
    }


def _load_cursor() -> dict[str, Any]:
    try:
        value = json.loads(_CURSOR_PATH.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            # Preserve progress when moving from the older cursor format instead of
            # silently sending the user back to the first UK batch.
            base = _default_cursor()
            for key in ("phase", "country_index", "offset", "checked", "complete", "skipped_shards", "last_error"):
                if key in value:
                    base[key] = value[key]
            return base
    except Exception:
        pass
    return _default_cursor()


def _save_cursor(state: dict[str, Any]) -> None:
    state["version"] = _CURSOR_VERSION
    _CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CURSOR_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_CURSOR_PATH)


def _advance_cursor(state: dict[str, Any]) -> None:
    state["country_index"] = int(state.get("country_index") or 0) + 1
    state["offset"] = 0
    if state["country_index"] >= len(EUROPE_WIKIDATA_COUNTRIES):
        if state.get("phase") == "direct":
            state["phase"] = "subclasses"
            state["country_index"] = 0
        else:
            state["complete"] = True


def company_universe_cursor_status() -> dict[str, Any]:
    state = _load_cursor()
    idx = min(max(0, int(state.get("country_index") or 0)), len(EUROPE_WIKIDATA_COUNTRIES) - 1)
    return {**state, "country": EUROPE_WIKIDATA_COUNTRIES[idx][0] if EUROPE_WIKIDATA_COUNTRIES else ""}


def fetch_wikidata_europe_companies(limit: int = 100, offset: int = 0, timeout: int = 12) -> list[dict[str, Any]]:
    """Return the next resumable Company Universe batch.

    Public SPARQL is allowed to be flaky. After the bounded request retries are exhausted,
    LeadScope records that shard and advances instead of freezing the entire local indexer.
    `offset` remains only for compatibility with the worker; the persisted cursor is real.
    """
    del offset
    limit = max(1, min(int(limit), 150))
    state = _load_cursor()
    attempts = 0
    max_attempts = len(EUROPE_WIKIDATA_COUNTRIES) * 2 + 2
    while not state.get("complete") and attempts < max_attempts:
        attempts += 1
        idx = int(state.get("country_index") or 0)
        if idx >= len(EUROPE_WIKIDATA_COUNTRIES):
            _advance_cursor(state)
            _save_cursor(state)
            continue
        country_name, country_qid = EUROPE_WIKIDATA_COUNTRIES[idx]
        current_offset = max(0, int(state.get("offset") or 0))
        try:
            batch = fetch_wikidata_country_batch(
                country_qid=country_qid,
                country_name=country_name,
                limit=limit,
                offset=current_offset,
                timeout=timeout,
                include_subclasses=state.get("phase") == "subclasses",
            )
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError, ValueError) as exc:
            shard = f"{state.get('phase','direct')}:{country_name}:{current_offset}"
            skipped = list(state.get("skipped_shards") or [])
            if shard not in skipped:
                skipped.append(shard)
            state["skipped_shards"] = skipped[-100:]
            state["last_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            # The request has already exhausted its own retries, so defer this shard and
            # move on. Missing one page is better than blocking every other country.
            state["offset"] = current_offset + limit
            if current_offset >= 12000:
                _advance_cursor(state)
            _save_cursor(state)
            continue

        raw_count = int(batch.get("raw_count") or 0)
        state["last_error"] = ""
        state["checked"] = int(state.get("checked") or 0) + raw_count
        state["offset"] = current_offset + limit
        if raw_count == 0 or raw_count < limit or current_offset >= 12000:
            _advance_cursor(state)
        _save_cursor(state)
        items = list(batch.get("items") or [])
        if items:
            return items
    _save_cursor(state)
    return []
