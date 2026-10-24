from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
USER_AGENT = "LeadScope/7.13 (public company-universe indexing; https://github.com/breddpit228-stack/LeadScope)"

CORDIS_ZIP_URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"
CORDIS_DATASET_URL = "https://data.europa.eu/data/datasets/cordis-eu-research-projects-under-horizon-europe-2021-2027"
CORDIS_ZIP_PATH = DATA_DIR / "cordis-HORIZONprojects-csv.zip"
CORDIS_CACHE_PATH = DATA_DIR / "cordis_horizon_companies.json"
CORDIS_CURSOR_PATH = DATA_DIR / "cordis_horizon_index_state.json"

CORDIS_PROGRAMMES: dict[str, dict[str, Any]] = {
    "horizon": {
        "label": "Horizon Europe",
        "zip_url": CORDIS_ZIP_URL,
        "dataset_url": CORDIS_DATASET_URL,
        "zip_path": CORDIS_ZIP_PATH,
        "cache_path": CORDIS_CACHE_PATH,
        "cursor_path": CORDIS_CURSOR_PATH,
    },
    "h2020": {
        "label": "Horizon 2020",
        "zip_url": "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
        "dataset_url": "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
        "zip_path": DATA_DIR / "cordis-h2020projects-csv.zip",
        "cache_path": DATA_DIR / "cordis_h2020_companies.json",
        "cursor_path": DATA_DIR / "cordis_h2020_index_state.json",
    },
}

COUNTRY_CODES = {
    "AL":"Albania","AD":"Andorra","AT":"Austria","BY":"Belarus","BE":"Belgium","BA":"Bosnia and Herzegovina",
    "BG":"Bulgaria","HR":"Croatia","CY":"Cyprus","CZ":"Czechia","DK":"Denmark","EE":"Estonia","FI":"Finland",
    "FR":"France","DE":"Germany","EL":"Greece","GR":"Greece","HU":"Hungary","IS":"Iceland","IE":"Ireland",
    "IT":"Italy","XK":"Kosovo","LV":"Latvia","LI":"Liechtenstein","LT":"Lithuania","LU":"Luxembourg","MT":"Malta",
    "MD":"Moldova","MC":"Monaco","ME":"Montenegro","NL":"Netherlands","MK":"North Macedonia","NO":"Norway",
    "PL":"Poland","PT":"Portugal","RO":"Romania","SM":"San Marino","RS":"Serbia","SK":"Slovakia","SI":"Slovenia",
    "ES":"Spain","SE":"Sweden","CH":"Switzerland","UA":"Ukraine","UK":"United Kingdom","GB":"United Kingdom",
}
EUROPE_COUNTRIES = set(COUNTRY_CODES.values()) | {"Czech Republic", "Republic of Moldova", "United Kingdom of Great Britain and Northern Ireland"}


def _programme(programme: str) -> dict[str, Any]:
    key = str(programme or "horizon").strip().lower()
    if key not in CORDIS_PROGRAMMES:
        raise ValueError(f"Unknown CORDIS programme: {programme}")
    return CORDIS_PROGRAMMES[key]


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _pick(row: dict[str, Any], *names: str) -> str:
    by_key = {_norm_key(k): str(v or "").strip() for k, v in row.items()}
    for name in names:
        value = by_key.get(_norm_key(name), "")
        if value:
            return value
    return ""


def _country_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper in COUNTRY_CODES:
        return COUNTRY_CODES[upper]
    if raw == "Czech Republic":
        return "Czechia"
    if raw == "Republic of Moldova":
        return "Moldova"
    if raw == "United Kingdom of Great Britain and Northern Ireland":
        return "United Kingdom"
    return raw


def _website(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or "@" in raw or raw.lower() in {"n/a", "na", "none", "-"}:
        return ""
    if raw.startswith("www."):
        raw = "https://" + raw
    if not raw.startswith(("http://", "https://")):
        if "." not in raw or " " in raw:
            return ""
        raw = "https://" + raw
    return raw


def _is_private_company(row: dict[str, Any]) -> bool:
    activity = _pick(row, "activityType", "activity type", "organisationType", "organizationType", "type").lower()
    sme = _pick(row, "SME", "isSME", "smeFlag").lower()
    if activity in {"prc", "private for-profit", "private for profit", "private company", "company"}:
        return True
    if "private" in activity and ("profit" in activity or "company" in activity):
        return True
    return sme in {"true", "yes", "1", "y"} and activity not in {"pub", "hes", "hie", "rec", "oth"}


def _decode_csv(data: bytes) -> tuple[str, str]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:12000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","
    return text, delimiter


def _organization_members(zf: zipfile.ZipFile) -> list[str]:
    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    org = [n for n in names if "organi" in Path(n).name.lower()]
    if org:
        return org
    out: list[str] = []
    for name in names:
        try:
            head = zf.read(name)[:20000].decode("utf-8-sig", errors="ignore").lower()
        except Exception:
            continue
        if ("organisation" in head or "organization" in head) and ("activitytype" in head or "sme" in head):
            out.append(name)
    return out


def extract_cordis_companies(
    zip_path: Path,
    programme_label: str = "Horizon Europe",
    dataset_url: str = CORDIS_DATASET_URL,
) -> list[dict[str, Any]]:
    """Parse European private for-profit CORDIS organisations with a public website."""
    companies: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        members = _organization_members(zf)
        for member in members:
            text, delimiter = _decode_csv(zf.read(member))
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            for row in reader:
                if not _is_private_company(row):
                    continue
                name = _pick(row, "name", "organisationName", "organizationName", "legalName", "shortName")
                country = _country_name(_pick(row, "country", "countryName", "organisationCountry", "organizationCountry"))
                url = _website(_pick(row, "organizationURL", "organisationURL", "organisationUrl", "organizationUrl", "website", "webSite", "url"))
                if not name or not url or not country or country not in EUROPE_COUNTRIES:
                    continue
                key = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url.lower())).split("/")[0].split(":")[0]
                if not key:
                    continue
                oid = _pick(row, "organisationID", "organizationID", "orgID", "id", "pic")
                activity = _pick(row, "activityType", "activity type", "organisationType", "organizationType")
                sme = _pick(row, "SME", "isSME", "smeFlag")
                tags = ["CORDIS", programme_label, "Private for-profit"]
                if activity:
                    tags.append(activity)
                if sme.lower() in {"true", "yes", "1", "y"}:
                    tags.append("SME")
                item = {
                    "name": name,
                    "website": url,
                    "description": f"Private for-profit organisation participating in {programme_label} research and innovation projects.",
                    "tags": tags,
                    "source_url": dataset_url,
                    "extra": {
                        "country": country,
                        "city": _pick(row, "city", "town"),
                        "cordis_organisation_id": oid,
                        "cordis_activity_type": activity,
                        "cordis_programme": programme_label,
                    },
                }
                existing = companies.get(key)
                if not existing or (not existing["extra"].get("country") and country):
                    companies[key] = item
    return list(companies.values())


def _save_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_cursor(programme: str = "horizon") -> dict[str, Any]:
    path = Path(_programme(programme)["cursor_path"])
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return {"offset": max(0, int(value.get("offset") or 0)), "complete": bool(value.get("complete"))}
    except Exception:
        pass
    return {"offset": 0, "complete": False}


def _save_cursor(programme: str, value: dict[str, Any]) -> None:
    _save_json_atomic(Path(_programme(programme)["cursor_path"]), value)


def ensure_cordis_cache(
    progress: Callable[[str], None] | None = None,
    force: bool = False,
    programme: str = "horizon",
) -> list[dict[str, Any]]:
    cfg = _programme(programme)
    label = str(cfg["label"])
    zip_path = Path(cfg["zip_path"])
    cache_path = Path(cfg["cache_path"])
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not force:
        try:
            value = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(value, list) and value:
                return value
        except Exception:
            pass

    if progress:
        progress(f"Downloading CORDIS {label} open dataset…")
    if force or not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
        tmp = zip_path.with_suffix(".zip.tmp")
        with requests.get(str(cfg["zip_url"]), stream=True, timeout=(10, 90), headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            with tmp.open("wb") as fh:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress and downloaded % (5 * 1024 * 1024) < len(chunk):
                        progress(f"Downloading CORDIS {label} · {downloaded // (1024 * 1024)} MB…")
        tmp.replace(zip_path)

    if progress:
        progress(f"Parsing private companies from CORDIS {label}…")
    companies = extract_cordis_companies(zip_path, programme_label=label, dataset_url=str(cfg["dataset_url"]))
    _save_json_atomic(cache_path, companies)
    _save_cursor(programme, {"offset": 0, "complete": False})
    if progress:
        progress(f"CORDIS {label} prepared · {len(companies):,} private organisations with websites")
    return companies


def fetch_cordis_companies(
    programme: str = "horizon",
    limit: int = 250,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    items = ensure_cordis_cache(progress=progress, programme=programme)
    state = _load_cursor(programme)
    if state.get("complete"):
        return []
    start = max(0, int(state.get("offset") or 0))
    limit = max(1, min(int(limit), 1000))
    batch = items[start:start + limit]
    new_offset = start + len(batch)
    complete = new_offset >= len(items)
    _save_cursor(programme, {"offset": new_offset, "complete": complete})
    return batch


def fetch_cordis_horizon_companies(limit: int = 250, progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    return fetch_cordis_companies("horizon", limit=limit, progress=progress)


def fetch_cordis_h2020_companies(limit: int = 250, progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    return fetch_cordis_companies("h2020", limit=limit, progress=progress)


def cordis_source_status(programme: str = "horizon") -> dict[str, Any]:
    cfg = _programme(programme)
    state = _load_cursor(programme)
    total = 0
    cache_path = Path(cfg["cache_path"])
    zip_path = Path(cfg["zip_path"])
    try:
        if cache_path.exists():
            value = json.loads(cache_path.read_text(encoding="utf-8"))
            total = len(value) if isinstance(value, list) else 0
    except Exception:
        pass
    return {
        **state,
        "programme": programme,
        "label": str(cfg["label"]),
        "total": total,
        "cached": cache_path.exists(),
        "zip_cached": zip_path.exists(),
    }


def cordis_h2020_source_status() -> dict[str, Any]:
    return cordis_source_status("h2020")
