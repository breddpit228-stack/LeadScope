from __future__ import annotations

import time
from typing import Any, Callable

from .cordis_source import (
    cordis_h2020_source_status,
    cordis_source_status,
    fetch_cordis_h2020_companies,
    fetch_cordis_horizon_companies,
)
from .library_sources import company_universe_cursor_status, fetch_wikidata_europe_companies
from .storage import company_count
from .universe_merge import backfill_universe_taxonomy, merge_company_items

StatusCallback = Callable[[dict[str, Any]], None]


def _emit(callback: StatusCallback | None, **patch: Any) -> None:
    if callback:
        callback({"heartbeat_at": time.time(), **patch})


def run_company_universe_index(target: int = 10000, status_callback: StatusCallback | None = None) -> dict[str, Any]:
    """Grow Company Universe using a resilient public-source cascade.

    Cascade: Wikidata -> CORDIS Horizon Europe -> CORDIS Horizon 2020.
    Sources are merged by canonical domain. A source is left when it is exhausted or
    repeatedly returns domains already present in the local Universe.
    """
    target = max(1000, min(int(target), 10000))
    total_added = 0
    total_updated = 0
    checked = 0
    source_history: list[str] = []

    _emit(status_callback, source="taxonomy", message="Normalizing existing Company Universe profiles…")
    taxonomy = backfill_universe_taxonomy(limit=max(target * 2, 20000))
    taxonomy_updated = int(taxonomy.get("updated") or 0)
    _emit(
        status_callback,
        taxonomy_updated=taxonomy_updated,
        message=f"Normalized {taxonomy_updated:,} existing profiles · starting public source cascade…",
    )

    # Phase 1: Wikidata.
    zero_add_streak = 0
    wikidata_batches = 0
    while company_count() < target and wikidata_batches < 120:
        cursor = company_universe_cursor_status()
        if cursor.get("complete"):
            break
        country = str(cursor.get("country") or "public source")
        phase = str(cursor.get("phase") or "direct")
        source_offset = int(cursor.get("offset") or 0)
        _emit(
            status_callback,
            source="wikidata",
            cursor_country=country,
            cursor_phase=phase,
            cursor_offset=source_offset,
            message=f"Wikidata · {country} · {phase} · offset {source_offset:,} · {company_count():,} / {target:,}",
        )
        items = fetch_wikidata_europe_companies(limit=100, timeout=12)
        if not items:
            break
        result = merge_company_items(
            items,
            limit=max(0, target - company_count()),
            source_name="Wikidata · European businesses with official websites",
        )
        added = int(result.get("added") or 0)
        updated = int(result.get("updated") or 0)
        total_added += added
        total_updated += updated
        checked += len(items)
        wikidata_batches += 1
        zero_add_streak = zero_add_streak + 1 if added == 0 else 0
        if "wikidata" not in source_history:
            source_history.append("wikidata")
        _emit(
            status_callback,
            source="wikidata",
            added=total_added,
            updated=total_updated,
            taxonomy_updated=taxonomy_updated,
            checked=checked,
            message=f"{company_count():,} indexed · Wikidata batch +{added} new / {updated} enriched",
        )
        if zero_add_streak >= 4:
            _emit(
                status_callback,
                source="wikidata",
                message=f"Wikidata is yielding duplicates · switching source at {company_count():,} companies…",
            )
            break
        time.sleep(0.25)

    def run_cordis_phase(
        *,
        source_key: str,
        label: str,
        fetcher: Callable[..., list[dict[str, Any]]],
        status_reader: Callable[[], dict[str, Any]],
        source_name: str,
    ) -> None:
        nonlocal total_added, total_updated, checked
        if company_count() >= target:
            return
        zero_streak = 0

        def progress(message: str) -> None:
            _emit(
                status_callback,
                source=source_key,
                added=total_added,
                updated=total_updated,
                taxonomy_updated=taxonomy_updated,
                checked=checked,
                message=message,
            )

        while company_count() < target:
            state = status_reader()
            _emit(
                status_callback,
                source=source_key,
                cordis_programme=label,
                cordis_offset=int(state.get("offset") or 0),
                cordis_total=int(state.get("total") or 0),
                message=f"CORDIS {label} · {company_count():,} / {target:,} indexed…",
            )
            items = fetcher(limit=300, progress=progress)
            if not items:
                break
            result = merge_company_items(
                items,
                limit=max(0, target - company_count()),
                source_name=source_name,
            )
            added = int(result.get("added") or 0)
            updated = int(result.get("updated") or 0)
            total_added += added
            total_updated += updated
            checked += len(items)
            zero_streak = zero_streak + 1 if added == 0 else 0
            if source_key not in source_history:
                source_history.append(source_key)
            _emit(
                status_callback,
                source=source_key,
                added=total_added,
                updated=total_updated,
                taxonomy_updated=taxonomy_updated,
                checked=checked,
                message=f"{company_count():,} indexed · CORDIS {label} batch +{added} new / {updated} enriched",
            )
            if zero_streak >= 5:
                _emit(
                    status_callback,
                    source=source_key,
                    message=f"CORDIS {label} is yielding duplicates · moving to next source…",
                )
                break
            time.sleep(0.15)

    # Phase 2: current Horizon Europe data.
    run_cordis_phase(
        source_key="cordis_horizon",
        label="Horizon Europe",
        fetcher=fetch_cordis_horizon_companies,
        status_reader=cordis_source_status,
        source_name="CORDIS Horizon Europe · private organisations",
    )

    # Phase 3: historical Horizon 2020 participant organisations.
    run_cordis_phase(
        source_key="cordis_h2020",
        label="Horizon 2020",
        fetcher=fetch_cordis_h2020_companies,
        status_reader=cordis_h2020_source_status,
        source_name="CORDIS Horizon 2020 · private organisations",
    )

    reached = company_count() >= target
    result = {
        "company_count": company_count(),
        "target": target,
        "added": total_added,
        "updated": total_updated,
        "taxonomy_updated": taxonomy_updated,
        "checked": checked,
        "target_reached": reached,
        "sources": source_history,
    }
    _emit(
        status_callback,
        source="complete" if reached else "exhausted",
        **result,
        message=(
            f"Company Universe reached {company_count():,} companies"
            if reached
            else f"Public sources exhausted at {company_count():,} companies · next source required"
        ),
    )
    return result
