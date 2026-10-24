from __future__ import annotations

import time
from typing import Any, Callable

from .cordis_source import cordis_source_status, fetch_cordis_horizon_companies
from .library_sources import company_universe_cursor_status, fetch_wikidata_europe_companies
from .storage import company_count
from .universe_merge import backfill_universe_taxonomy, merge_company_items

StatusCallback = Callable[[dict[str, Any]], None]


def _emit(callback: StatusCallback | None, **patch: Any) -> None:
    if callback:
        callback({"heartbeat_at": time.time(), **patch})


def run_company_universe_index(target: int = 10000, status_callback: StatusCallback | None = None) -> dict[str, Any]:
    """Grow Company Universe using a resilient source cascade.

    Wikidata is the broad identity source. When it stops producing unique domains for a
    few batches, the indexer switches to CORDIS Horizon Europe private organisations.
    One exhausted/flaky source never blocks the rest of the local indexing run.
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

    # Phase 1: Wikidata. Stop early when repeated batches only produce domains we already have.
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

    # Phase 2: CORDIS Horizon Europe official open data.
    if company_count() < target:
        cordis_zero_streak = 0

        def cordis_progress(message: str) -> None:
            _emit(
                status_callback,
                source="cordis",
                added=total_added,
                updated=total_updated,
                taxonomy_updated=taxonomy_updated,
                checked=checked,
                message=message,
            )

        while company_count() < target:
            state = cordis_source_status()
            _emit(
                status_callback,
                source="cordis",
                cordis_offset=int(state.get("offset") or 0),
                cordis_total=int(state.get("total") or 0),
                message=f"CORDIS Horizon Europe · {company_count():,} / {target:,} indexed…",
            )
            items = fetch_cordis_horizon_companies(limit=300, progress=cordis_progress)
            if not items:
                break
            result = merge_company_items(
                items,
                limit=max(0, target - company_count()),
                source_name="CORDIS Horizon Europe · private organisations",
            )
            added = int(result.get("added") or 0)
            updated = int(result.get("updated") or 0)
            total_added += added
            total_updated += updated
            checked += len(items)
            cordis_zero_streak = cordis_zero_streak + 1 if added == 0 else 0
            if "cordis" not in source_history:
                source_history.append("cordis")
            _emit(
                status_callback,
                source="cordis",
                added=total_added,
                updated=total_updated,
                taxonomy_updated=taxonomy_updated,
                checked=checked,
                message=f"{company_count():,} indexed · CORDIS batch +{added} new / {updated} enriched",
            )
            if cordis_zero_streak >= 5:
                break
            time.sleep(0.15)

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
