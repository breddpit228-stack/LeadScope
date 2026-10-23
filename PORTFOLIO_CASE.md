# Portfolio case — LeadScope v5

## Problem

A list of company facts is not enough for outbound or account research. A useful workflow must answer four separate questions without mixing them:

- What is confirmed?
- What changed or looks commercially relevant?
- Why does this account fit *our* offer?
- What should a human consider doing next?

## Solution

LeadScope builds four layers:

### 1. Evidence-backed company facts
Services, customers, decision roles, markets and concrete public proof are extracted from official company pages. Each evidence item retains its source URL and is validated against the saved page text.

### 2. Observable commercial signals
LeadScope searches both core company pages and a limited number of public signal-oriented pages such as careers/news/partnership/case-study pages. Signals are labeled observations and never converted directly into buying intent.

### 3. Offer-relative fit
The user configures their offer, value proposition and ICP. The score is deterministic and explainable, including geography, category, required/preferred criteria, offer adjacency, timing signals, evidence depth, public proof and team-size fit.

### 4. Hypotheses & action
Only after facts are verified does the LLM generate cautious hypotheses. Each hypothesis includes what it is based on, target role, confidence and a recommended manual next action. Outreach is generated from the same verified context.

## Scale demo

The workspace can seed up to 1,000 real European companies from a public startup/accelerator dataset. Batch mode performs real crawl/extraction/scoring sequentially and stores results in SQLite. Demo activity is visibly labeled `DEMO`; it is not represented as genuine user activity.

## Tech

- Python
- FastAPI
- SQLite
- Gemini structured output
- Trafilatura / BeautifulSoup
- HTML/CSS/vanilla JS
- resumable local batch workflow


## Signal quality layer

Commercial signals are not treated equally. The application deterministically ranks each source-backed observation by:
- signal strength (high / medium / low),
- freshness (current / recent / dated / unknown),
- relevance to the configured offer (high / medium / low).

Only sufficiently strong, fresh/recent, offer-relevant signals are eligible to drive an opportunity hypothesis. This prevents old partnerships or generic compliance statements from becoming misleading sales angles.
