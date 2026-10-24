# Portfolio case — LeadScope

## Context

I wanted a portfolio project that demonstrated more than “I can call an AI API”. The goal was to build a small B2B workflow where automation, public data, AI-assisted research and product decisions all had to work together.

The initial version was a website-research dashboard: enter a company domain, crawl public pages, extract facts and generate a fit score.

That worked technically, but it exposed a more important product problem:

> Before researching an account deeply, a user first needs to know **which companies are worth researching at all**.

That changed the product direction.

## Product redesign

The current workflow is:

`Create workspace → Discover → Shortlist → Research → Results`

A workspace represents one prospecting task, for example:

`Fintech · Poland · B2B · 201–500 employees`

The user defines a target market, discovers matching companies, shortlists only the accounts worth evaluating and then spends deep-research resources on that smaller set.

This avoids running expensive AI research across thousands of companies that may never matter.

## Key product decisions

### 1. Company discovery before deep research

LeadScope maintains a local **Company Universe** assembled from public sources instead of searching the web from scratch every time a user opens Discover.

Current source cascade:

- European public startup/company seed data
- Wikidata companies with official websites
- CORDIS Horizon Europe private for-profit organisations
- CORDIS Horizon 2020 private for-profit organisations as an additional fallback
- manually analysed companies

Records are merged by canonical domain. The same company can therefore receive missing country/category/source metadata from another source without creating another row.

Deep AI research only begins after the user shortlists a company.

### 2. Missing data is not a match

An early matcher could produce results such as “83% Strong Match” even when company size was unknown.

That was mathematically possible because industry + location + B2B points could outweigh the missing criterion, but it was product-wise misleading.

The matching layer was redesigned around explicit required evidence:

- Industry
- Location
- Business model
- Company size

Each criterion is marked as:

`match / partial / unknown / mismatch`

If a required criterion is unknown or contradicted, the company cannot be shown as a Strong Match even when its raw weighted score is high.

### 3. “Is Fintech” is different from “serves Fintech clients”

Keyword matching created another false-positive class: software consultancies mentioning Fintech customers could appear to be Fintech companies themselves.

LeadScope now distinguishes:

- **Primary industry**
- **Adjacent industry**
- **Serves industry clients**

Service providers that merely work with a target industry are moved to Broader Candidates rather than inflating the Strong Matches count.

### 4. Company profile quality is different from ICP match

Discover separates:

- **Data quality / completeness** — how much useful public company data exists
- **Profile match** — how well verified attributes match the current workspace

A well-documented company can still be a poor match, while a relevant-looking company with missing required evidence remains incomplete until verified.

### 5. Facts, signals and hypotheses are separate

The research layer keeps three concepts distinct:

**Facts**
- products/services
- target customers
- markets
- commercial proof

**Observable signals**
- product launches
- partnerships
- expansion
- hiring
- leadership changes
- customer/case-study evidence

**Hypotheses**
- possible commercial opportunity
- target role
- recommended outreach angle

Signals are never presented as proof that a company is actively buying.

### 6. Research failure is not bad fit

Some domains are poor research sources: social/login-heavy pages, storefronts, blocked sites or pages that time out.

Instead of turning missing evidence into `0/100`, LeadScope separates:

- bad fit
- insufficient public evidence
- source issue

This prevents technical access problems from becoming false business conclusions.

## Reliability work

Building the workflow exposed practical engineering problems that were useful learning opportunities:

- browser freezes caused by self-triggering DOM observers
- duplicate async renders when switching Workspace tabs
- state loss after page refresh
- research jobs blocked by slow company websites
- source indexers stalling on one public-data request
- public-data sources producing duplicate domains rather than new companies

The current version includes:

- no global recursive MutationObservers in Workspace UI
- tab/workspace/search/page state persistence for the browser session
- abort/cancellation protection for stale Discover renders
- sequential research queues
- bounded HTTP timeouts and source fallback behaviour
- resumable Company Universe indexing
- multi-source indexing with deduplication
- GitHub Actions regression/smoke tests

## Decision model after research

Research results are workspace-specific rather than global.

The same company may be attractive in one workspace and irrelevant in another.

LeadScope separates:

- **Fit** — researched match to this workspace
- **Timing** — strength/freshness of relevant company signals
- **Confidence** — evidence quality
- **Priority** — combined review ranking

The user-facing result states are:

- Recommended
- Watch
- Potential
- Not a fit

## Tech stack

- Python
- FastAPI
- SQLite
- requests
- Trafilatura / BeautifulSoup
- public structured datasets
- LLM-assisted structured research/outreach
- HTML / CSS / vanilla JavaScript
- GitHub Actions

## What I would not claim

LeadScope is a portfolio product, not a production replacement for Apollo, Clay or Dealroom.

The local Company Universe is intentionally built from public/open data and does not claim the breadth, enrichment depth or SLA of commercial company-data vendors.

Likewise, observable company signals are not described as verified purchase intent.

## What the project demonstrates

The strongest part of the project is not the number of companies in the database. It is the end-to-end reasoning behind the workflow:

- defining a B2B problem
- iterating after usability failures
- building a multi-source data pipeline
- handling missing/weak evidence explicitly
- using AI only where it adds value
- combining deterministic scoring with LLM-assisted research
- designing a workflow that remains explainable to a human reviewer

## CV-ready summary

> Built a local-first B2B prospect discovery and account-research application in Python/FastAPI. Designed a multi-source European company indexing pipeline with domain-level deduplication, evidence-aware prospect matching, public website research, commercial-signal scoring and workspace-specific outreach recommendations.
