# Project Insight User Stories and Acceptance Criteria

**Last updated:** August 4, 2026

These stories formalize behavior implemented in the current Project Insight product. Acceptance criteria use Given, When, and Then statements so each behavior can be reviewed or tested.

## 1. Generate a company brief

**User story:** As a researcher, I want to enter a company name so I can receive one structured brief instead of assembling information across several sites.

**Acceptance criteria**

* Given a nonempty company name, when I submit the search, then the frontend sends the company to the analysis API.
* Given a successful response, when the report loads, then I can see the company summary, positioning, SWOT analysis, competitors, current developments, and sources supported by the response.
* Given an empty search field, when I submit it, then no analysis request is sent.

## 2. Select a recognized company

**User story:** As a researcher, I want company suggestions while I type so I can choose the intended organization and reduce spelling errors.

**Acceptance criteria**

* Given at least two typed characters, when autocomplete data is available, then matching company suggestions are displayed.
* Given a selected suggestion, when I start the search, then its company name is used for the analysis request.
* Given an unavailable autocomplete service, when I continue typing, then the search field remains usable without suggestions.

## 3. Receive the correct company report type

**User story:** As a researcher, I want the report to distinguish public companies from private startups so I do not see unsupported public market metrics.

**Acceptance criteria**

* Given a ticker and supporting financial evidence, when classification completes, then the company is treated as public.
* Given no public listing, when classification completes, then the company receives the private company report structure.
* Given a ticker without enough financial evidence, when classification completes, then the report identifies the status as unknown rather than silently labeling the company private.

## 4. Verify revenue and other financial claims

**User story:** As a researcher, I want reported revenue and financial context to appear with traceable sources so I can verify important figures.

**Acceptance criteria**

* Given a public company with available market data, when the report renders, then revenue and supported financial measures appear in the public company sections.
* Given retrieved source metadata, when I review the report, then source titles and direct links are available in the sources section.
* Given that a financial field is unavailable, when the response is generated, then the product does not invent a precise value to fill the gap.

## 5. Understand source coverage and freshness

**User story:** As a researcher, I want to know how many sources informed the report and how recent they are so I can judge whether further verification is needed.

**Acceptance criteria**

* Given a report with retrieved sources, when a supported section renders, then it displays the number of sources used.
* Given dated sources, when freshness information is calculated, then the most recent available date is shown.
* Given no usable source date, when the section renders, then the product does not fabricate one.

## 6. Review the competitive landscape

**User story:** As a founder or analyst, I want to see named competitors and areas of overlap so I can understand how the company is positioned.

**Acceptance criteria**

* Given a valid structured response, when the competitive section renders, then the report shows available competitor names and supporting details.
* Given overlapping product information in the response, when a competitor is shown, then the overlap is presented in a readable format.
* Given incomplete competitor data, when the response is normalized, then malformed string or list values do not break the report.

## 7. Save and reopen research

**User story:** As a repeat researcher, I want to save a report so I can reopen it without running the same paid analysis again.

**Acceptance criteria**

* Given a generated report, when I save it, then the report is added to the Research Library in browser local storage.
* Given a saved report, when I refresh the page, then the saved item remains available in the same browser.
* Given that I save the same company again, when storage updates, then the current saved version replaces the duplicate entry.

## 8. Maintain favorites and recent searches

**User story:** As a researcher comparing several companies, I want favorites and search history so I can return to relevant companies quickly.

**Acceptance criteria**

* Given a report or company entry, when I mark it as a favorite, then it appears in the favorites group.
* Given completed searches, when I open the Research Library, then recent companies appear in reverse chronological order.
* Given more than ten completed searches, when history updates, then only the ten most recent unique entries are retained.

## 9. Export a report

**User story:** As a researcher, I want to export the brief as a PDF so I can share or review it outside the application.

**Acceptance criteria**

* Given a generated report, when I choose Export PDF, then the browser print flow opens.
* Given the print layout, when the report is previewed, then navigation, search, and application controls are removed from the output.
* Given a completed print action, when I save as PDF, then the report content is available as a portable document.

## 10. Recover from provider failures

**User story:** As a researcher, I want a clear error when analysis cannot be completed so I know whether to try again.

**Acceptance criteria**

* Given an upstream data or AI provider failure, when the analysis endpoint cannot complete, then it returns a controlled error response.
* Given an unsuccessful analysis response, when the frontend receives it, then the page shows an error rather than a partial report presented as complete.
* Given a later successful request, when I search again, then the previous error is cleared and the new report can render.
