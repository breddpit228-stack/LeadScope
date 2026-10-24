# LeadScope — AI-assisted B2B prospect discovery & account research

LeadScope is a local-first prospecting workspace that helps turn a target market into a shortlist of companies worth researching.

Instead of treating an AI-generated company summary as the product, LeadScope separates **company discovery**, **public evidence**, **workspace fit**, **commercial timing**, and **outreach hypotheses** into distinct layers.

## Product workflow

`Create workspace → Discover → Shortlist → Research → Results`

### 1. Create a workspace

Define the market you care about:

- industry / category
- country or region
- B2B / B2C model
- company-size range
- optional keywords
- what you sell

A workspace is one prospecting task, for example:

`Fintech · Poland · B2B · 201–500 employees`

### 2. Discover

LeadScope searches a local **Company Universe** built from multiple public sources and ranks companies against the workspace criteria.

The current data pipeline includes:

- public European startup/company seed data
- Wikidata companies with official websites
- CORDIS / Horizon Europe private for-profit organisations
- manually analysed companies

Records are merged by canonical domain so a second source can enrich an existing company instead of creating another copy.

Discover intentionally distinguishes:

- **Strong matches** — required criteria are actually supported
- **Broader candidates** — potentially relevant, but one or more criteria are partial, unknown or mismatched

Missing evidence is never silently treated as a match. For example, if a workspace requires `201–500 employees` and public company size is unknown, the company cannot become a Strong Match simply from industry + geography.

### 3. Shortlist

Selected companies move into one working queue instead of separate “selected” and “research queue” screens.

A company can be:

- Ready to research
- Researching
- Completed
- Source issue

Research runs sequentially so one slow or inaccessible website does not block the rest of the shortlist.

### 4. Research

LeadScope crawls public company pages and stores an evidence-backed factual layer:

- company brief
- products / services
- target customers and roles
- markets
- commercial proof
- observable company signals
- saved source pages

Research distinguishes **facts** from **hypotheses**. Observable signals are not treated as proof of buying intent.

### 5. Results

After research, each company receives workspace-specific decision support:

- **Fit** — how well the researched company matches this workspace
- **Timing** — strength and freshness of relevant observable signals
- **Confidence** — quality of the evidence behind the decision
- **Priority** — combined ranking for review

Result states are intentionally human-readable:

- **Recommended**
- **Watch**
- **Potential**
- **Not a fit**

The same company can receive a different Fit in another workspace because the target market and offer are different.

## Evidence and scoring principles

LeadScope is deliberately conservative about missing or weak data.

- Official/public company sources are preferred.
- Facts and hypotheses are stored separately.
- Missing information stays missing rather than being guessed.
- Weak or inaccessible sources do not receive a fake `0/100` fit score.
- A company that merely **serves Fintech clients** is not automatically classified as a Fintech company.
- Unknown required criteria prevent a company from being presented as a Strong Match.
- Commercial signals are ranked by strength, freshness and relevance.
- Outreach is generated only after the factual layer and workspace context are available.

## Company Universe

LeadScope maintains its own local company index instead of performing a live external search every time Discover opens.

The indexing pipeline:

`public sources → canonical-domain merge → basic enrichment → taxonomy → Discover`

The local Universe can grow toward a configured indexing target while the product remains usable. Deep AI research is **not** run across the whole Universe; it is reserved for companies the user actually shortlists.

This keeps the expensive workflow focused:

`large indexed universe → relevant candidates → shortlist → deep research → prioritised results`

## Source quality

Not every URL is a useful research source.

LeadScope distinguishes between usable corporate websites and problematic sources such as:

- login-heavy/social pages
- storefronts / marketplaces
- thin public sites
- inaccessible or timed-out domains

If public evidence is insufficient, the product reports the source problem instead of turning missing data into a negative business conclusion.

## Architecture

**Backend**

- Python
- FastAPI
- SQLite
- background indexing / research workers

**Data & crawling**

- `requests`
- BeautifulSoup / Trafilatura
- public structured datasets
- canonical-domain deduplication and enrichment

**AI layer**

- LLM-assisted structured research and workspace-specific outreach when configured locally
- deterministic validation/scoring around the model output

**Frontend**

- lightweight HTML / CSS / vanilla JavaScript
- no frontend framework required

## Local Windows setup

The repository intentionally does **not** contain API keys or the local SQLite database.

1. Clone/download the repository.
2. Configure the local AI provider if you want deep research/outreach.
3. Run `start_windows.bat`.
4. Open `http://127.0.0.1:8000` if the browser does not open automatically.

For future updates, `update_and_start.bat` updates the code while keeping local environment files and the database.

## Why I built it

The project started as a simple company-website research tool and evolved after testing the workflow.

A dashboard full of scores and account lists was not enough: a user first needs to answer **which companies are worth researching at all**. That led to the current workspace model:

`define market → discover companies → shortlist → research → decide`

During development I also changed the matching model after finding that keyword-based classification could confuse a software consultancy that serves Fintech clients with a Fintech company itself. The current matching layer distinguishes primary industry from adjacent/service relationships and treats unknown required criteria explicitly.

## Portfolio summary

A concise, truthful project description:

> Built a local-first B2B prospect discovery and account-research application in Python/FastAPI. Designed a multi-source European company indexing pipeline with canonical-domain deduplication, workspace-based prospect matching, evidence-backed website research, commercial-signal scoring and contextual outreach recommendations.

Selected implementation highlights:

- designed the `Discover → Shortlist → Research → Results` product workflow
- built a multi-source company data pipeline and local Company Universe
- implemented evidence-aware ICP/profile matching with required-criteria gating
- separated verified facts, observable signals and sales hypotheses
- implemented Fit / Timing / Confidence / Priority decision support
- added source-quality handling for blocked, thin and inappropriate research domains
- built non-blocking sequential research queues and resumable company indexing
- added automated regression/smoke tests through GitHub Actions

## Scope

LeadScope is a portfolio product, not a claim to be a production replacement for commercial data platforms such as Apollo, Clay or Dealroom.

The goal is to demonstrate product thinking, automation, data engineering, AI-assisted research, evidence handling and practical B2B workflow design in one working application.
