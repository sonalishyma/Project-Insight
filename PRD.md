# Project Insight Product Requirements Document

**Product:** Project Insight<br>
**Owner:** Sonali Singh<br>
**Status:** Deployed product<br>
**Last updated:** August 4, 2026

## Product purpose

Company research is fragmented across market feeds, SEC filings, articles, and social sources. Project Insight reduces that work to one query and returns a structured, source grounded brief for a public company or private startup.

The product is designed for research assistance. It does not provide financial advice and it does not replace verification of primary sources.

## Users and needs

**Investors** need a fast view of financial performance, valuation context, market sentiment, recent events, and competitive position before deciding where to research further.

**Founders and operators** need a consistent way to review competitors, positioning, funding signals, market activity, and areas of overlap.

**Job seekers** need a concise view of company momentum, business health, funding or earnings context, and current developments before an interview or offer decision.

These personas are product hypotheses derived from the research problem and use cases. The project record does not yet include completed stakeholder interviews or moderated usability sessions.

## Product goals

1. Turn a company name into a useful brief without requiring the user to assemble information across multiple sites.
2. Preserve source links and freshness information so users can verify important claims.
3. Adapt the report structure to the evidence available for public and private companies.
4. Present results in a format that can be saved, revisited, and exported.
5. Fail clearly when an upstream source or AI provider is unavailable.

## Scope delivered

### Company search and classification

The user can enter a company name or select an autocomplete suggestion. The backend resolves the company, gathers market evidence, and classifies it as public, private, or unknown. An unknown classification uses the public research path while clearly communicating that verified financial data was not available.

### Source retrieval and transformation

The backend combines current web research with market data, SEC context, news, and public sentiment sources. The pipeline normalizes this material into separate public and private company contexts before sending it to the AI model.

### Structured analysis

OpenRouter produces a structured report through tool calling. Pydantic response models validate the result before the FastAPI endpoint returns it to the React dashboard. Core sections include a company summary, positioning, SWOT analysis, competitors, current developments, confidence information, and cited sources.

### Public company report

When reliable listing and financial evidence are available, the report can include ticker and exchange details, revenue, market capitalization, financial ratios, annual performance, stock history, analyst sentiment, earnings context, and SEC events.

### Private company report

When no public listing is found, the report uses a startup focused structure for stage, funding, investors, traction, milestones, customers, and growth signals. Unsupported traditional public company metrics are not shown as if they exist.

### Research library and export

Users can save reports, maintain favorites, and revisit recent searches in browser local storage. Reports can be exported through a print optimized PDF flow. The current product has no account system or shared database.

## Functional requirements

1. Accept a nonempty company name and submit it to the analysis endpoint.
2. Determine whether public market evidence supports a public, private, or unknown classification.
3. Retrieve current sources and retain the title, link, and date when available.
4. Route the evidence through the correct public or private analysis schema.
5. Validate the structured response before rendering the report.
6. Show source count and freshness information where source metadata is available.
7. Provide direct source links for verification.
8. Store saved reports, favorites, and recent searches locally in the browser.
9. Provide a print optimized PDF export.
10. Return a clear error when an upstream data or AI provider prevents report generation.

Detailed user stories and acceptance criteria are maintained in [USER_STORIES.md](./USER_STORIES.md).

## Iteration and product decisions

The first working version established the core loop from company query to a structured report. Subsequent work improved public company detection, expanded ticker coverage, added typo tolerance, and separated public and private report paths so unavailable public metrics did not create misleading private company reports.

A later trust and usability pass added source freshness notes, classification provenance, PDF export, saved research, clearer error responses, and a more focused report order. Media and social features were revised or removed when APIs, terms of service, rate limits, or presentation quality made them unreliable. Compare mode was deferred until the single company workflow is stable.

The next planned validation stage is to instrument the search and report funnel, collect in product feedback, and conduct moderated sessions before making claims about user behavior. Planned work is documented separately in [insight_v2_roadmap.md](./insight_v2_roadmap.md).

## Nonfunctional requirements

**Traceability:** AI generated claims should be grounded in retrieved context and accompanied by source links.

**Data integrity:** Unsupported fields should be omitted rather than filled from model memory.

**Resilience:** Provider failures should return actionable errors instead of appearing as unexplained browser or CORS failures.

**Performance:** Independent source requests should run concurrently where practical. The product should monitor report latency before setting a formal service target.

**Accessibility and responsiveness:** Search, navigation, report sections, and export controls should remain usable on desktop and mobile layouts.

## Dependencies and constraints

The product depends on OpenRouter, Tavily, Yahoo Finance data accessed through yfinance, SEC EDGAR, and other public source endpoints. Availability, rate limits, account credit, and provider policy can affect completeness and latency.

Social platform APIs and employer rating services were not treated as dependable core inputs because of paid access, restricted public APIs, scraping concerns, and changing terms of service.

## Measurement plan

The product does not yet have validated behavioral metrics. The next release should measure search initiation, successful report generation, section engagement, save and export actions, feedback, latency, and upstream cost.

The proposed primary measure is a completed useful lookup: a report is generated and followed by a meaningful action such as section engagement, a save, an export, or positive feedback. Confidence score calibration should be tested against audited report accuracy before the score is treated as a validated trust signal.

## Release acceptance

A release is acceptable when a valid company query produces a schema valid report or a clear error, source links remain available for supported claims, public and private companies receive the appropriate report structure, local library actions persist after refresh, and the report can be exported without navigation chrome.
