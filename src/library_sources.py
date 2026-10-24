from __future__ import annotations

import random
import time
from typing import Any

import requests

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "LeadScope/7.7 (public company-universe indexing; https://github.com/breddpit228-stack/LeadScope)"
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def _wikidata_request(query: str, timeout: int, retries: int = 4) -> dict[str, Any]:
    """Run a bounded public Wikidata query with polite transient-error retries."""
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            response = requests.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
                timeout=max(8, int(timeout)),
            )
            if response.status_code in _TRANSIENT_STATUS:
                retry_after = response.headers.get("Retry-After")
                if retry_after and str(retry_after).isdigit():
                    delay = min(12.0, float(retry_after))
                else:
                    delay = min(12.0, (1.6 ** attempt) + random.uniform(0.15, 0.75))
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
            time.sleep(min(10.0, (1.7 ** attempt) + random.uniform(0.15, 0.7)))
    if last_error:
        raise last_error
    raise RuntimeError("Wikidata returned no usable response")


def fetch_wikidata_europe_companies(limit: int = 150, offset: int = 0, timeout: int = 28) -> list[dict[str, Any]]:
    """Fetch a small, paginated batch of European businesses with official websites.

    The query deliberately avoids a global ORDER BY because sorting the entire Wikidata
    company graph is expensive and was causing local indexing to stall. These are basic
    index records only; LeadScope still performs independent enrichment and research.
    """
    limit = max(1, min(int(limit), 250))
    offset = max(0, int(offset))
    query = f'''SELECT DISTINCT ?company ?companyLabel ?website ?countryLabel ?industryLabel WHERE {{
      VALUES ?kind {{ wd:Q4830453 wd:Q783794 }}
      ?company wdt:P31 ?kind ;
               wdt:P856 ?website ;
               wdt:P17 ?country .
      ?country wdt:P30 wd:Q46 .
      OPTIONAL {{ ?company wdt:P452 ?industry . }}
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
        country = str((row.get("countryLabel") or {}).get("value") or "").strip()
        industry = str((row.get("industryLabel") or {}).get("value") or "").strip()
        item_url = str((row.get("company") or {}).get("value") or "").strip()
        if not name or not website or website in seen:
            continue
        seen.add(website)
        tags = [x for x in [industry, "Wikidata"] if x]
        description = f"European company indexed from Wikidata. Official website: {website}."
        if industry:
            description = f"European company indexed from Wikidata · industry: {industry}."
        out.append({
            "name": name,
            "website": website,
            "description": description,
            "tags": tags,
            "extra": {"country": country, "city": "", "wikidata_url": item_url},
        })
    return out
