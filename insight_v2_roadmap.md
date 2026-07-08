# Insight v2 — Product Roadmap & Experimentation Plan

| | |
|---|---|
| **Product** | Insight — AI company-research reports (project-insight-roan.vercel.app) |
| **Owner** | Sonali Singh |
| **Status** | Draft — forward roadmap for the shipped v1 |
| **Date** | July 2026 |

---

## 1. Where v1 stands

v1 proved the core loop: enter a company, and an LLM aggregates pre-vetted sources (Forbes, Yahoo Finance, CNN, and similar) into a single health report — company snapshot (market cap, P/E, key financials), stock chart, competitive landscape, and recent media coverage — with a private-company mode (funding rounds, timeline) and an **AI confidence score** derived from source count and cross-source agreement. The user it serves is someone who wants a clear picture of a company without doing the multi-tab research themselves.

What v1 deliberately does not yet have, and what v2 exists to fix: **no instrumentation** (I can't see the funnel, so I can't prioritize on evidence), **an unvalidated trust layer** (the confidence score is a reasonable heuristic, but it has never been audited against ground truth), **no reason to return** (every session is a one-shot lookup), and **no compliance framing** (a tool that surfaces P/E ratios to would-be investors needs to say clearly what it is and isn't).

## 2. The v2 thesis

**v1 proved Insight can generate a report. v2's job is to prove the report can be trusted — and only then to give people a reason to come back.** AI research tools fail on credibility before they fail on capability, so the sequencing is deliberate: trust → depth → habit. This is the same design philosophy as the confidence score itself (and the same trust-first stance as my other product work): never ask the user to believe the output more than the evidence supports.

## 3. Explicit non-goals for v2

- **No buy/sell recommendations or personalized investment advice** — regulatory exposure and a trust liability; Insight describes companies, it does not advise.
- **No general chat interface.** The structured report *is* the product; a blank prompt box helps power users and confuses the target user (novices want structure).
- **No real-time streaming market data** — expensive, and not what the "give me a clear picture" user needs.
- **No user accounts until a feature requires them.** Accounts arrive with watchlists (Later), not before.

## 4. Roadmap

### Now (weeks 0–6) — Trust & Calibration

- **Sprint 0 — Instrumentation.** PostHog (or Vercel Analytics) events: `search_initiated`, `report_generated`, `section_expanded`, `confidence_viewed`, `feedback_submitted`; log latency and API cost per report. Rationale: every later decision in this document should be checkable against data; this ships first so nothing else flies blind.
- **Feedback loop on every report.** "Was this useful?" thumbs plus a "Report an inaccuracy" link. The second control quietly doubles as a free, user-generated accuracy dataset.
- **Inline source citations + freshness stamps.** Each report section links the sources behind it and shows when the data was retrieved. The confidence score says *how much* to trust; citations show *why*.
- **Accuracy audit v0 — the flagship credibility move.** Monthly, sample ~20 well-known companies, compare Insight's reported figures (P/E, market cap) against a reference source, and measure the error rate **by confidence band**. The question that turns a heuristic into a product claim: *are high-confidence reports actually more accurate?* If yes, the score is calibrated and the methodology gets published in the case study. If no, fixing that becomes v2's top engineering priority.
- **Compliance framing.** A visible "informational, not investment advice" disclaimer and a data-attribution page.

### Next (weeks 6–14) — Depth & Comparison

- **Compare mode.** Side-by-side Company A vs. Company B: snapshot deltas, shared competitors, coverage tone. Rationale: the natural next question after any single report is "…compared to what?"
- **Sector context.** Show where a company's key ratios sit against sector medians, so a novice knows whether a P/E of 38 is high *for this sector* — this converts raw numbers into judgment, which is the product's actual promise.
- **One-page PDF export.** The shareable artifact (with attribution footer — a lightweight growth loop).
- **Private-company depth.** Standardized funding timelines; investor lists where sourced.

### Later (months 4–6) — Retention & Habit

- **Report history**, then **watchlists with a "what changed" digest**: re-run a watched company's report on a schedule and surface the diff (new coverage, valuation moves, funding events). This is the feature that converts a one-shot tool into a research companion — and it's deliberately last, because retention investment before proven trust puts the cart before the horse.
- **Lightweight accounts** arrive only here, because watchlists require them.

### Cross-cutting — AI quality & unit economics

- **Gold eval set:** ~25 reference company reports re-run on every prompt or model change — regression testing for the AI layer, so quality changes are measured, not vibes.
- **Model routing & caching:** a cheap/fast model for extraction and formatting, a frontier model for synthesis only; cache same-company lookups for 24h. Target: cut cost per report ~50% and improve p50 latency.
- **Cost guardrail:** track $/report with a budget alert. A report tool whose unit economics are invisible is a demo, not a product.

## 5. Prioritization rationale (the tradeoffs, stated)

Calibration beats new features because trust is the differentiator — an uncalibrated confidence score is a liability wearing a feature's clothes. Compare-mode beats a chat interface because it matches the report paradigm and the novice user; chat is the intuitive-but-wrong move here. Retention is sequenced last on purpose: a "what changed" digest built on unaudited reports would just automate the delivery of possible errors. Everything is sized for a single builder — this roadmap is honest about capacity, which is why each phase is small and gated on the previous one.

## 6. Metrics

- **North Star: completed useful lookups** — a report generated *and* a positive/neutral engagement signal (section expansion, positive feedback, or export). Counts value delivered, not pageviews.
- **Funnel:** visit → search → report → section expansion → feedback/return; watch the largest drop-off each week.
- **Per-theme KPIs:** Trust — feedback rate, inaccuracy-report rate, calibration gap (error rate in high- vs. low-confidence reports). Depth — compare-mode adoption, exports per report. Habit — 14-day return rate, watchlist adds.
- **Guardrails:** report completion rate, p50 latency, $/report, error/timeout rate.

## 7. Experiment design — does explaining the confidence score earn trust?

**Premise (honest):** the confidence score is Insight's differentiator, but it has never been validated against user behavior. Before building more trust UI, test whether the trust UI does anything.

- **Hypothesis.** Reports that display the confidence score *with a plain-language source explanation* ("87 — built from 14 vetted sources, 11 corroborating the key figures") will earn a higher positive-feedback rate than reports showing the bare number, because users can see *why* to trust the output, not just how much.
- **Variants.** A (control): current bare numeric score. B: score + source-count explainer. Optional C (if traffic ever allows): no score at all — the bold null check on whether the score matters, worth running precisely because the answer isn't obvious.
- **Assignment.** Visitor-level, cookie-sticky, 50/50 at first report render. The explainer is computed from metadata Insight already has, so B adds **zero** AI cost or latency — guardrails should confirm that.
- **Primary metric:** positive-feedback rate per generated report. **Secondary:** section-expansion depth, 14-day return, explainer/tooltip interaction. **Guardrails:** report completion rate, p50 latency, $/report.
- **Power, honestly.** Detecting a 10-point lift (e.g., 40% → 50% positive feedback) at α = 0.05 and 80% power needs roughly **390 reports per arm (~780 total)**. At v1's current traffic that could take months, so the test is **gated**: it launches only when 7-day report volume supports a ≤ 8-week runtime. Below the gate, run the qualitative version first — five moderated sessions plus a one-question on-report micro-survey ("How much do you trust this report? 1–5") — which is cheaper and answers the same directional question. Claiming an underpowered A/B result would be exactly the false confidence this product exists to prevent.
- **Decision rule.** Ship B if the primary metric lifts ≥ 5 points with no guardrail regression. If flat, the qualitative trust signal breaks the tie; if *that's* flat too, run C — maybe the score isn't the trust lever, and the citations are.
- **Risks.** Novelty effect (mitigate: minimum 4-week runtime past the gate); feedback rate as a proxy for trust (mitigate: micro-survey triangulation); low-traffic false positives (mitigated by the gate itself).

## 8. Sequencing & gates

Sprint 0 (instrumentation, feedback, disclaimer) → Trust block (citations, audit v0) → **gate: is the confidence score calibrated?** → Depth block (compare, sector context, export) → **gate: does 7-day volume support the A/B?** → run experiment → Habit block (history, watchlists, accounts). Each gate is a real decision point, not a formality — if calibration fails, Depth waits.

## 9. Risks & dependencies

OpenAI API cost and model deprecations (mitigated by routing + the eval set, which makes model swaps testable); source availability and terms (prefer official APIs and licensed feeds over scraping as usage grows); hallucinated financial figures (the audit + citations are the mitigation, and the reason Trust ships first); single-builder bandwidth (scoped accordingly); and the standing product risk that a research tool is judged by its worst error, not its average one — which is why every phase of this roadmap reports to the trust theme.
