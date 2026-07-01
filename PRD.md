# Insight — Product Requirements Document

## Problem

Researching a company today means opening eight tabs — a stock screener, SEC filings,
Crunchbase, Glassdoor, Twitter, and three news sites — and manually synthesizing what
you find. That's slow for anyone who needs a fast, structured read on a company: an
investor sizing up a position, a founder scoping competitors, or a candidate deciding
whether to take an offer.

Insight collapses that research loop into one query: type a company name, get a
structured, source-grounded decision brief in under a minute.

## Personas

| Persona | Job to be done | What they need from the brief |
|---|---|---|
| **Investor** | Decide whether a public company is worth researching further | Valuation multiples, margin trends, analyst sentiment, competitive positioning |
| **Founder** | Understand the competitive landscape before building or pitching | Competitor overlap, market sizing, positioning, funding comps for private players |
| **Job seeker** | Decide whether to take an interview or offer | Growth signals, funding health, culture/sentiment signals, "what's happening now" |

The same underlying data (financials, SWOT, news, sources) serves all three — the
differences are in which section they scan first, not in what's collected.

## What shipped (v1)

- **Dual-mode reports.** Public companies get financial statements, ratios, analyst
  sentiment, and earnings. Private companies get a startup-native view instead
  (funding rounds, hiring signals, milestones, traction) rather than an empty
  financials section — the pipeline detects company type and branches the whole
  report structure, not just hides a chart.
- **Source-grounded generation.** Every AI-written section (SWOT, positioning,
  summary, competitive landscape) is generated from live web search results fetched
  at query time, not model memory — with a confidence score and, as of this update,
  a per-section "based on N sources, most recent [date]" footnote so a reader can
  gauge freshness without leaving the page.
- **Market Voices.** Analyst rating actions (upgrades/downgrades) blended with
  StockTwits retail sentiment — investor and general-sentiment signals side by side.
  Job seekers get a rough proxy for company momentum for free from data already
  collected for investors.
- **Research Library.** Saved reports, favorites, and search history persisted
  locally — repeat lookups don't require re-querying paid APIs, and a user building
  a comparison set (e.g. a founder scoping five competitors) has a place to keep them.
- **Export to PDF.** One button; the report strips chrome (nav, search, sidebar) and
  prints cleanly — the artifact is meant to be shared, not just viewed once.

## What was deliberately cut (and why)

- **Social media embeds (Twitter/Instagram post previews).** Reading platform APIs
  now requires paid tiers ($200+/mo for X) with no free public read access for
  arbitrary accounts, and scraping violates ToS. Cut rather than shipped as a
  brittle/gray-area feature. Revisit via search-snippet retrieval (Tavily indexes
  tweet/post content) + Twitter's free oEmbed endpoint for the one platform where
  a clean, ToS-compliant embed is actually possible.
- **Employer rating card (Glassdoor/Indeed score).** Same constraint — neither
  platform exposes a public ratings API, and both actively block scraping. Cut for
  v1; the plan is search-snippet retrieval (rating appears in the search snippet
  itself, which is legitimate RAG, not scraping) blended with hiring-signal proxies
  already in the data (employee growth, layoff news) rather than depending on one
  fragile source.
- **Compare mode (two companies side by side).** Real user need — investors and
  job seekers both naturally compare — but deferred until the single-company report
  is fully solid, since compare mode roughly doubles the surface area of every
  existing bug.

## Success metrics (if this were shipped to real users)

- **Time to first insight**: seconds from query submit to first meaningful content
  render (currently gated by the slowest upstream API call in the pipeline).
  Confidence-footnote and streaming partial results are the next lever here.
  - **Note (as of 2026-07-01):** first-call latency currently also depends on
    OpenRouter account credit balance — a request that exceeds the available
    balance now fails fast with a clear `502` instead of a silent CORS-masked
    "Failed to fetch," but the underlying fix for *speed* is unrelated to this
    incident and still open.
- **Repeat-query rate**: % of searches that hit the Research Library cache instead
  of re-querying — a direct proxy for whether the tool earns a second visit.
- **Confidence-score correlation**: whether reports with score >80 get saved/
  favorited at a higher rate than <60 — validates whether the score is actually
  signal or just decoration.

## Prioritization rationale

Everything in v1 is either (a) needed to make *both* company types (public/private)
usable, or (b) cheap to add given data already being fetched for another section
(Market Voices' retail sentiment is nearly free once analyst data is already in
hand). Anything requiring a paid API tier or ToS-risky scraping was cut rather than
shipped in a degraded form — a broken or gray-area integration is worse for
trust than an honestly-missing section.
