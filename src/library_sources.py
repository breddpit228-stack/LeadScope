from __future__ import annotations

from typing import Any

import requests

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "LeadScope/6.0 (public company-library indexing; https://github.com/breddpit228-stack/LeadScope)"


def fetch_wikidata_europe_companies(limit: int = 250, offset: int = 0, timeout: int = 40) -> list[dict[str, Any]]:
    """Fetch a small, paginated batch of European businesses with official websites.

    This intentionally uses only basic index fields. It does not claim the records are
    researched or sales-ready. Deep enrichment remains a separate LeadScope step.
    """
    limit = max(1, min(int(limit), 500))
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
    ORDER BY ?company
    LIMIT {limit}
    OFFSET {offset}'''
    response = requests.get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    bindings = response.json().get("results", {}).get("bindings", [])
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
