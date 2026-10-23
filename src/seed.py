from __future__ import annotations

import requests

EUROPE_DATA_URL = "https://cdn.jsdelivr.net/gh/yigitmeteozcan/startups@main/data/by-region/europe.json"


def fetch_europe_seed(timeout: int = 30) -> list[dict]:
    r = requests.get(EUROPE_DATA_URL, timeout=timeout, headers={"User-Agent": "LeadScopePortfolio/4.0"})
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list):
        raise RuntimeError("Europe seed dataset returned an unexpected format")
    return [x for x in payload if isinstance(x, dict) and x.get("website") and x.get("name")]
