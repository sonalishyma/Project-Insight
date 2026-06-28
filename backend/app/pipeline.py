import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import OpenAI

from .schemas import (
    AnalystSentiment, AnnualPoint, Competitor, CompanySnapshot, EarningsInfo, EarningsPoint,
    FinancialRatios, FundingInfo, FundingRound, GrowthSignals,
    MarketAnalysis, Milestone, MarketTraction, Positioning, Source,
    StockPoint, SwotAnalysis,
)
from . import search, market_data, edgar

load_dotenv()

# ── Public company tool ───────────────────────────────────────────────────────

_PUBLIC_TOOL = {
    "type": "function",
    "function": {
        "name": "output_analysis",
        "description": "Output structured market analysis for a publicly traded company.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "4-6 sentence 'What's Happening Now' covering: current market position "
                        "and momentum, recent earnings performance, important recent news or events, "
                        "recent product launches or strategic moves, stock performance drivers, "
                        "and current investor sentiment."
                    ),
                },
                "market_size": {
                    "type": "string",
                    "description": "Total addressable market estimate, e.g. '$500B global EV market'.",
                },
                "positioning": {
                    "type": "object",
                    "properties": {
                        "overview": {"type": "string", "description": "1-2 sentence positioning overview grounded in retrieved articles. Must reference a specific fact, number, or event from the sources."},
                        "primary_customer_base": {"type": "string", "description": "Who the main customers are, based on evidence in the retrieved context."},
                        "competitive_advantage": {"type": "string", "description": "The company's core moat as evidenced by the sources — cite a metric, product, or recent event."},
                        "brand_perception": {"type": "string", "description": "How the market perceives this brand, with specific evidence from the retrieved articles."},
                        "pricing_strategy": {"type": "string", "description": "Their pricing approach with concrete evidence from the sources."},
                        "business_model": {"type": "string", "description": "How the company generates revenue, citing specific revenue streams from the context."},
                        "market_differentiation": {"type": "string", "description": "What sets them apart, with direct evidence from the sources."},
                    },
                    "required": ["overview", "primary_customer_base", "competitive_advantage", "brand_perception", "pricing_strategy", "business_model", "market_differentiation"],
                },
                "swot": {
                    "type": "object",
                    "properties": {
                        "strengths": {"type": "array", "items": {"type": "string"}, "description": "3-5 internal strengths grounded in the retrieved sources. Each must reference a specific metric, product, or event (e.g. 'Services revenue grew 14% YoY per Q2 earnings'). No generic statements without specific evidence."},
                        "weaknesses": {"type": "array", "items": {"type": "string"}, "description": "3-5 internal weaknesses with specific evidence — named products underperforming, cited margin compression, regulatory actions, etc."},
                        "opportunities": {"type": "array", "items": {"type": "string"}, "description": "3-5 external opportunities cited in the retrieved articles — market size figures, named trends, competitor weaknesses."},
                        "threats": {"type": "array", "items": {"type": "string"}, "description": "3-5 external threats — named competitors gaining share, macro risks, specific regulatory pressures cited in sources."},
                    },
                    "required": ["strengths", "weaknesses", "opportunities", "threats"],
                },
                "competitors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "note": {"type": "string", "description": "Why they compete, performance comparison, and key differentiator."},
                            "overlapping_products": {"type": "array", "items": {"type": "string"}, "description": "2-3 products or services that directly overlap."},
                        },
                        "required": ["name", "note", "overlapping_products"],
                    },
                    "description": "3-5 main competitors.",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}}, "required": ["title", "url"]},
                    "description": "Sources from the web search context that informed this analysis.",
                },
                "confidence_score": {
                    "type": "integer",
                    "description": "0-100 confidence. 90-100: rich recent data. 70-89: good coverage minor gaps. 50-69: significant gaps or older data. 0-49: very limited info.",
                },
                "financial_summary": {
                    "type": "string",
                    "description": "3-4 sentence interpretation of financial health: revenue/earnings trajectory, profitability vs industry, valuation assessment, biggest financial risk or strength. Use actual numbers.",
                },
            },
            "required": ["summary", "market_size", "positioning", "swot", "competitors", "sources", "confidence_score", "financial_summary"],
        },
    },
}

# ── Private company tool ──────────────────────────────────────────────────────

_PRIVATE_TOOL = {
    "type": "function",
    "function": {
        "name": "output_analysis",
        "description": "Output structured market analysis for a private or early-stage company.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "4-6 sentence overview of this private company: what it does, its current momentum, "
                        "recent milestones or news, notable customers or partners, and its position in the market. "
                        "Ground every claim in the retrieved sources."
                    ),
                },
                "market_size": {
                    "type": "string",
                    "description": "Total addressable market this company is targeting, e.g. '$12B wildfire detection market'.",
                },
                "stage": {
                    "type": "string",
                    "description": "Company funding stage: 'Pre-Seed', 'Seed', 'Series A', 'Series B', 'Series C', 'Series D+', 'Pre-IPO', 'Bootstrapped', or 'Unknown'.",
                },
                "funding": {
                    "type": "object",
                    "properties": {
                        "total_raised": {"type": "string", "description": "Total funding raised to date, e.g. '$47M'."},
                        "latest_round": {"type": "string", "description": "Most recent round type, e.g. 'Series B'."},
                        "latest_amount": {"type": "string", "description": "Amount of the most recent round."},
                        "lead_investor": {"type": "string", "description": "Lead investor in the most recent round."},
                        "all_investors": {"type": "array", "items": {"type": "string"}, "description": "All known investors across all rounds."},
                        "rounds": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "round_type": {"type": "string"},
                                    "amount": {"type": "string"},
                                    "date": {"type": "string"},
                                    "lead_investor": {"type": "string"},
                                },
                            },
                            "description": "Individual funding rounds in chronological order.",
                        },
                    },
                },
                "growth_signals": {
                    "type": "object",
                    "properties": {
                        "employee_count": {"type": "string", "description": "Current approximate headcount, e.g. '~250 employees'."},
                        "employee_growth_pct": {"type": "string", "description": "Employee growth percentage, e.g. '38'."},
                        "employee_growth_period": {"type": "string", "description": "Period for the growth figure, e.g. '12 months'."},
                        "hiring_activity": {"type": "string", "description": "Hiring activity level: 'High', 'Moderate', or 'Low', based on open roles and job postings signals."},
                        "open_positions": {"type": "string", "description": "Approximate number of open positions if known."},
                        "new_locations": {"type": "array", "items": {"type": "string"}, "description": "New office locations or expansions."},
                    },
                },
                "milestones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "year": {"type": "string"},
                            "event": {"type": "string"},
                        },
                        "required": ["year", "event"],
                    },
                    "description": "Key company milestones in chronological order: founding, funding rounds, product launches, expansions, customer wins.",
                },
                "market_traction": {
                    "type": "object",
                    "properties": {
                        "customers": {"type": "array", "items": {"type": "string"}, "description": "Named customers or client types mentioned in sources."},
                        "partnerships": {"type": "array", "items": {"type": "string"}, "description": "Named strategic partnerships."},
                        "arr": {"type": "string", "description": "Annual Recurring Revenue if publicly disclosed, e.g. '$8M ARR'."},
                        "estimated_revenue": {"type": "string", "description": "Revenue estimate if reported by credible sources."},
                        "mau": {"type": "string", "description": "Monthly Active Users if disclosed."},
                        "enterprise_clients": {"type": "array", "items": {"type": "string"}, "description": "Named enterprise clients."},
                    },
                },
                "positioning": {
                    "type": "object",
                    "properties": {
                        "overview": {"type": "string", "description": "1-2 sentence overview of this startup's market position with specific evidence from sources."},
                        "primary_customer_base": {"type": "string", "description": "Target customers with evidence from retrieved articles."},
                        "competitive_advantage": {"type": "string", "description": "Core differentiation — technology, team, partnerships, or market timing evidence from sources."},
                        "brand_perception": {"type": "string", "description": "How the startup is perceived: investor confidence, press sentiment, customer reviews if mentioned."},
                        "pricing_strategy": {"type": "string", "description": "Pricing model or strategy if known from sources."},
                        "business_model": {"type": "string", "description": "Revenue model — SaaS, marketplace, licensing, services, etc., with evidence from sources."},
                        "market_differentiation": {"type": "string", "description": "What makes this startup different from incumbents and other startups."},
                    },
                    "required": ["overview", "primary_customer_base", "competitive_advantage", "brand_perception", "pricing_strategy", "business_model", "market_differentiation"],
                },
                "swot": {
                    "type": "object",
                    "properties": {
                        "strengths": {"type": "array", "items": {"type": "string"}, "description": "3-5 strengths grounded in sources: named investors, product differentiation, traction metrics, team credentials, or market timing advantages."},
                        "weaknesses": {"type": "array", "items": {"type": "string"}, "description": "3-5 weaknesses: funding dependence, limited market data, competitive pressure, or specific challenges mentioned in sources."},
                        "opportunities": {"type": "array", "items": {"type": "string"}, "description": "3-5 market opportunities: addressable market size, competitor gaps, regulatory tailwinds, or technology trends from the sources."},
                        "threats": {"type": "array", "items": {"type": "string"}, "description": "3-5 threats: well-funded competitors, market saturation, fundraising risk, or macro headwinds from the sources."},
                    },
                    "required": ["strengths", "weaknesses", "opportunities", "threats"],
                },
                "competitors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "note": {"type": "string", "description": "Why they compete and how they differ — include funding stage, traction, or key advantages."},
                            "overlapping_products": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "note", "overlapping_products"],
                    },
                    "description": "3-5 competitors — include both startups and established players.",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}}, "required": ["title", "url"]},
                },
                "confidence_score": {
                    "type": "integer",
                    "description": "0-100 confidence based on availability of public information about this private company.",
                },
                "financial_summary": {
                    "type": "string",
                    "description": "3-4 sentence investor/partner commentary: funding runway assessment, growth trajectory signals, what the investor backing suggests about the company's trajectory, and the biggest opportunity or risk for the company.",
                },
            },
            "required": ["summary", "market_size", "stage", "positioning", "swot", "competitors", "sources", "confidence_score"],
        },
    },
}


# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _build_context(articles: list[dict], company: str, mdata: dict) -> str:
    context = search.format_context(articles)

    # SEC 8-K events — appended before financial data so LLM sees official filings
    if mdata.get("ticker"):
        events = edgar.fetch_recent_events(mdata["ticker"], cik=mdata.get("cik"))
        context += edgar.format_events_context(events, company)

    fin_lines = []
    if mdata.get("ticker"):
        fin_lines.append(f"\nVerified market data for {company} ({mdata['ticker']}):")
    for label, key in [
        ("Market Cap", "market_cap"), ("Revenue (TTM)", "revenue"),
        ("Net Income", "net_income"), ("Sector", "sector"),
        ("P/E Ratio", "pe_ratio"), ("Revenue Growth YoY", "revenue_growth"),
    ]:
        val = mdata.get(key)
        if val is not None:
            if key == "revenue_growth":
                fin_lines.append(f"  {label}: {float(val)*100:.1f}%")
            else:
                fin_lines.append(f"  {label}: {val}")
    if fin_lines:
        context += "\n" + "\n".join(fin_lines)
    return context


def _build_snapshot(mdata: dict) -> CompanySnapshot:
    return CompanySnapshot(
        ticker=mdata.get("ticker"),
        exchange=mdata.get("exchange"),
        sector=mdata.get("sector"),
        industry=mdata.get("industry"),
        ceo=mdata.get("ceo"),
        headquarters=mdata.get("headquarters"),
        employees=mdata.get("employees"),
        market_cap=mdata.get("market_cap"),
        revenue=mdata.get("revenue"),
        net_income=mdata.get("net_income"),
        operating_income=mdata.get("operating_income"),
        cash=mdata.get("cash"),
        total_debt=mdata.get("total_debt"),
        website=mdata.get("website"),
        logo_url=mdata.get("logo_url"),
        wiki_summary=mdata.get("wiki_summary"),
        wiki_url=mdata.get("wiki_url"),
        data_as_of=mdata.get("data_as_of"),
    )


def _normalize_competitor(c) -> dict:
    """Coerce LLM competitor output to a valid dict regardless of what the model returned."""
    if not isinstance(c, dict):
        return {"name": str(c), "note": "", "overlapping_products": []}
    ops = c.get("overlapping_products", [])
    if isinstance(ops, str):
        c["overlapping_products"] = [ops] if ops else []
    elif not isinstance(ops, list):
        c["overlapping_products"] = []
    return c


def _enrich_and_date(data: dict, articles: list[dict]) -> tuple[list, dict]:
    raw_competitors = [_normalize_competitor(c) for c in data.get("competitors", [])]
    with ThreadPoolExecutor(max_workers=5) as executor:
        enriched = list(executor.map(market_data.enrich_competitor, raw_competitors))
    article_dates: dict[str, str | None] = {a["url"]: a.get("date") for a in articles}
    return enriched, article_dates


# ── Public pipeline ───────────────────────────────────────────────────────────

def _run_public(company: str, client: OpenAI, mdata: dict, articles: list[dict]) -> MarketAnalysis:
    context = _build_context(articles, company, mdata)

    completion = client.chat.completions.create(
        model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        max_tokens=3000,
        temperature=0,
        seed=42,
        tools=[_PUBLIC_TOOL],
        tool_choice={"type": "function", "function": {"name": "output_analysis"}},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a financial research analyst producing a structured report. "
                    "CRITICAL RULE: every claim must be traceable to the web search context provided — "
                    "do not use general industry knowledge as a substitute for retrieved evidence. "
                    "If the sources do not cover a topic, omit that point rather than filling from memory. "
                    "Apply the same specificity bar to SWOT points and every positioning field as the summary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{context}\n\n"
                    f"Using ONLY the web search results and verified market data above, "
                    f"produce a structured market analysis for: {company}. "
                    "Every claim must be traceable to the context. Cite the sources used."
                ),
            },
        ],
    )

    data = json.loads(completion.choices[0].message.tool_calls[0].function.arguments)
    enriched, article_dates = _enrich_and_date(data, articles)

    return MarketAnalysis(
        company=company,
        company_type="public",
        summary=data["summary"],
        market_size=data["market_size"],
        positioning=Positioning(**data["positioning"]),
        swot=SwotAnalysis(**data["swot"]),
        competitors=[Competitor(**c) for c in enriched],
        sources=[Source(title=s["title"], url=s["url"], date=article_dates.get(s["url"])) for s in data.get("sources", [])],
        sources_count=len(articles),
        confidence_score=data.get("confidence_score", 50),
        financial_summary=data.get("financial_summary"),
        snapshot=_build_snapshot(mdata),
        financial_ratios=FinancialRatios(
            pe_ratio=mdata.get("pe_ratio"),
            pb_ratio=mdata.get("pb_ratio"),
            ps_ratio=mdata.get("ps_ratio"),
            ev_ebitda=mdata.get("ev_ebitda"),
            revenue_growth=mdata.get("revenue_growth"),
            earnings_growth=mdata.get("earnings_growth"),
            gross_margin=mdata.get("gross_margin"),
            operating_margin=mdata.get("operating_margin"),
            net_margin=mdata.get("net_margin"),
            roe=mdata.get("roe"),
            roa=mdata.get("roa"),
            eps=mdata.get("eps"),
            fcf=mdata.get("fcf_formatted"),
            debt_to_equity=mdata.get("debt_to_equity"),
            current_ratio=mdata.get("current_ratio"),
            quick_ratio=mdata.get("quick_ratio"),
            dividend_yield=mdata.get("dividend_yield"),
            data_as_of=mdata.get("data_as_of"),
        ),
        analyst_sentiment=AnalystSentiment(**mdata["analyst_sentiment"]) if mdata.get("analyst_sentiment") else None,
        earnings_info=EarningsInfo(**mdata["earnings_info"]) if mdata.get("earnings_info") else None,
        stock_history=[StockPoint(**p) for p in mdata.get("stock_history", [])],
        quarterly_earnings=[EarningsPoint(**p) for p in mdata.get("quarterly_earnings", [])],
        annual_data=[AnnualPoint(**p) for p in mdata.get("annual_data", [])],
    )


# ── Private pipeline ──────────────────────────────────────────────────────────

def _run_private(company: str, client: OpenAI, mdata: dict, articles: list[dict]) -> MarketAnalysis:
    context = search.format_context(articles)

    completion = client.chat.completions.create(
        model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        max_tokens=3500,
        temperature=0,
        seed=42,
        tools=[_PRIVATE_TOOL],
        tool_choice={"type": "function", "function": {"name": "output_analysis"}},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a startup research analyst producing a structured report for a private company. "
                    "Focus on: funding history, investor backing, employee and hiring growth, product traction, "
                    "customer wins, partnerships, and market positioning. "
                    "CRITICAL: use ONLY information from the web search context provided — do not hallucinate "
                    "funding amounts, investor names, or metrics not mentioned in the sources. "
                    "If a field is not supported by the sources, omit it. "
                    "For milestones, reconstruct the company timeline from any date-stamped events in the sources."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{context}\n\n"
                    f"Using ONLY the web search results above, produce a structured startup analysis for: {company}. "
                    "Extract all funding, investor, growth, traction, and milestone data you can find in the sources."
                ),
            },
        ],
    )

    data = json.loads(completion.choices[0].message.tool_calls[0].function.arguments)
    enriched, article_dates = _enrich_and_date(data, articles)

    # Parse funding
    raw_funding = data.get("funding") or {}
    funding = FundingInfo(
        total_raised=raw_funding.get("total_raised"),
        latest_round=raw_funding.get("latest_round"),
        latest_amount=raw_funding.get("latest_amount"),
        lead_investor=raw_funding.get("lead_investor"),
        all_investors=raw_funding.get("all_investors") or [],
        rounds=[FundingRound(**r) for r in (raw_funding.get("rounds") or [])],
    ) if raw_funding else None

    # Parse growth signals
    raw_growth = data.get("growth_signals") or {}
    growth_signals = GrowthSignals(**raw_growth) if raw_growth else None

    # Parse milestones
    milestones = [Milestone(**m) for m in (data.get("milestones") or [])]

    # Parse market traction
    raw_traction = data.get("market_traction") or {}
    market_traction = MarketTraction(**raw_traction) if raw_traction else None

    # Collect all investors for top-level field
    all_investors = raw_funding.get("all_investors") or [] if raw_funding else []

    return MarketAnalysis(
        company=company,
        company_type="private",
        stage=data.get("stage"),
        summary=data["summary"],
        market_size=data["market_size"],
        positioning=Positioning(**data["positioning"]),
        swot=SwotAnalysis(**data["swot"]),
        competitors=[Competitor(**c) for c in enriched],
        sources=[Source(title=s["title"], url=s["url"], date=article_dates.get(s["url"])) for s in data.get("sources", [])],
        sources_count=len(articles),
        confidence_score=data.get("confidence_score", 50),
        financial_summary=data.get("financial_summary"),
        snapshot=_build_snapshot(mdata),
        funding=funding,
        growth_signals=growth_signals,
        milestones=milestones,
        market_traction=market_traction,
        investors=all_investors,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def run(company: str) -> MarketAnalysis:
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )

    # Fetch market data first — determines public vs private classification
    mdata = market_data.fetch(company)
    is_public = bool(mdata.get("ticker") and mdata.get("market_cap"))
    print(f"[pipeline] {company}: ticker={mdata.get('ticker')}, market_cap={mdata.get('market_cap')}, is_public={is_public}", flush=True)

    if is_public:
        articles = search.fetch(company)
        return _run_public(company, client, mdata, articles)
    else:
        articles = search.fetch_private(company)
        return _run_private(company, client, mdata, articles)


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else "Apple"))
