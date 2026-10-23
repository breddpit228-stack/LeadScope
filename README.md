# LeadScope v5.4 — evidence-backed B2B account intelligence

LeadScope turns a company website into a structured research brief for sales/marketing review.

## What changed in v5.4

The product no longer treats a website summary as the final output. Research is split into explicit layers:

1. **Facts** — services, target customers, target roles, markets.
2. **Commercial proof** — metrics, case-study results, partner tiers, certifications, named customer proof when explicitly present.
3. **Observable signals** — hiring, product/AI investment, partnerships, expansion, pricing/product changes, customer proof, etc. Signals are source-backed but are **not** treated as buying intent.

4. **Signal quality ranking** — each commercial signal now receives deterministic **Strength**, **Freshness**, and **Offer relevance** labels. Old/weak/irrelevant signals remain visible as context but do not inflate timing score or drive opportunity hypotheses.
5. **Hypothesis gate** — opportunity hypotheses may only be built from signals that pass the minimum strength × freshness × relevance threshold.
4. **Offer fit** — deterministic scoring against the user's configured offer + ICP.
5. **Hypotheses** — clearly labeled inferences generated only from verified facts/signals, with `based_on`, target role, confidence and recommended action.
6. **Outreach** — generated only after the factual and hypothesis layers are separated.

## Minimal flow

Home screen:

`company website -> Analyze`

Full workspace:

- 1,000-company European seed workspace
- batch factual research + scoring
- Offer & ICP configuration
- activity log
- CSV export
- full Company Report page with Overview / Signals / Evidence / Outreach / Notes

## Offer & ICP

The default profile is explicitly a demo profile. Edit it in **Workspace -> Offer & ICP**:

- What do you sell?
- Value proposition
- Target roles
- Target countries / industries
- Required and preferred fit signals
- Buying/growth signals worth noticing
- Disqualifiers
- Team-size range

Saving the profile **recalculates previously researched company scores locally**. This does not spend additional Gemini quota.

## Research quality rules

- Official public company pages only.
- Evidence must be traceable to the exact saved source URL.
- Unsupported evidence is rejected by code.
- Facts and hypotheses are stored/rendered separately.
- Commercial signals are observations, never proof of buying intent.
- Missing information stays missing rather than being guessed.
- Batch mode does not generate outreach for all 1,000 companies; it focuses quota on factual extraction + scoring.

## Windows

1. Extract the ZIP.
2. Run `configure_gemini_windows.bat` and enter a **new local Gemini key**.
3. Run `start_windows.bat`.
4. Open `http://127.0.0.1:8000` if the browser does not open automatically.

The `.env` file is excluded from Git.

## Portfolio positioning

A truthful description:

> Built an evidence-backed B2B account research application that crawls public company pages, separates facts from commercial signals and hypotheses, scores accounts against a configurable offer/ICP, preserves source evidence, and supports batch research across a seeded European company workspace.

The prefilled activity marked `DEMO` is seeded product-demo activity and must not be presented as real customer usage.
