from __future__ import annotations

import random
import time
from typing import Any

import requests

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "LeadScope/7.8 (public company-universe indexing; https://github.com/breddpit228-stack/LeadScope)"
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}

# Ordered roughly by expected company-data density so a fresh LeadScope installation
# becomes useful quickly. Country-sharded queries are substantially cheaper and more
# reliable than asking WDQS to scan all of Europe for every page.
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


def _wikidata_request(query: str, timeout: int, retries: int = 4) -> dict[str, Any]:
    """Run a bounded public Wikidata query with polite transient-error retries."""
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
                timeout=max(8, int(timeout)),
            )
            if response.status_code in _TRANSIENT_STATUS:
                retry_after = response.headers.get("Retry-After")
                if retry_after and str(retry_after).isdigit():
                    delay = min(18.0, float(retry_after))
                else:
                    delay = min(14.0, (1.7 ** attempt) + random.uniform(0.2, 0.9))
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
            time.sleep(min(12.0, (1.8 ** attempt) + random.uniform(0.2, 0.8)))
    if last_error:
        raise last_error
    raise RuntimeError("Wikidata returned no usable response")


def _clean_number(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = int(float(text))
        return str(number) if number > 0 else ""
    except Exception:
        return ""


def fetch_wikidata_country_batch(
    country_qid: str,
    country_name: str,
    limit: int = 150,
    offset: int = 0,
    timeout: int = 26,
    include_subclasses: bool = False,
) -> dict[str, Any]:
    """Fetch one small country-sharded Wikidata company batch.

    Phase one reads direct instances of business/company. Phase two can include
    subclasses to widen coverage if the direct pass does not reach the local target.
    Records are still only *indexed*; they are not treated as deep research.
    """
    limit = max(1, min(int(limit), 250))
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

    payload = _wikidata_request(query, timeout=timeout, retries=4)
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
        description = wikidata_description
        if not description and industry:
            description = f"{country_name} company indexed from Wikidata · industry: {industry}."
        if not description:
            description = f"{country_name} company indexed from Wikidata with an official website."
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
    limit: int = 150,
    offset: int = 0,
    timeout: int = 26,
    include_subclasses: bool = False,
) -> list[dict[str, Any]]:
    return list(fetch_wikidata_country_batch(
        country_qid=country_qid,
        country_name=country_name,
        limit=limit,
        offset=offset,
        timeout=timeout,
        include_subclasses=include_subclasses,
    ).get("items") or [])


def fetch_wikidata_europe_companies(limit: int = 150, offset: int = 0, timeout: int = 28) -> list[dict[str, Any]]:
    """Compatibility helper retained for older callers.

    New Company Universe indexing uses country-sharded batches because they are more
    reliable and can resume deterministically between application restarts.
    """
    limit = max(1, min(int(limit), 250))
    country_index = (max(0, int(offset)) // limit) % len(EUROPE_WIKIDATA_COUNTRIES)
    country_name, country_qid = EUROPE_WIKIDATA_COUNTRIES[country_index]
    country_offset = (max(0, int(offset)) // (limit * len(EUROPE_WIKIDATA_COUNTRIES))) * limit
    return fetch_wikidata_country_companies(
        country_qid,
        country_name,
        limit=limit,
        offset=country_offset,
        timeout=timeout,
        include_subclasses=False,
    )
