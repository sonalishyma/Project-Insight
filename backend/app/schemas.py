from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    company: str = Field(min_length=1, max_length=100)


class Source(BaseModel):
    title: str
    url: str
    date: str | None = None


class SocialLinks(BaseModel):
    twitter_url: str | None = None
    linkedin_url: str | None = None
    instagram_url: str | None = None


class RecentSignal(BaseModel):
    platform: str          # "twitter" | "linkedin" | "web"
    text: str               # snippet/post text
    url: str
    date: str | None = None


class Positioning(BaseModel):
    overview: str
    primary_customer_base: str
    competitive_advantage: str
    brand_perception: str
    pricing_strategy: str
    business_model: str
    market_differentiation: str


class SwotAnalysis(BaseModel):
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    threats: list[str]


class Competitor(BaseModel):
    name: str
    note: str
    ticker: str | None = None
    market_cap: str | None = None
    revenue: str | None = None
    industry: str | None = None
    logo_url: str | None = None
    overlapping_products: list[str] = []


class StockPoint(BaseModel):
    date: str
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    change: float | None = None
    change_pct: float | None = None


class EarningsPoint(BaseModel):
    quarter: str
    revenue: float | None = None
    net_income: float | None = None


class AnnualPoint(BaseModel):
    year: str
    revenue: float | None = None
    net_income: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    fcf: float | None = None
    eps: float | None = None


class FinancialRatios(BaseModel):
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    eps: float | None = None
    fcf: str | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    dividend_yield: float | None = None
    data_as_of: str | None = None


class AnalystRatingAction(BaseModel):
    date: str | None = None
    firm: str | None = None
    action: str | None = None
    from_grade: str | None = None
    to_grade: str | None = None
    current_price_target: float | None = None
    prior_price_target: float | None = None


class AnalystSentiment(BaseModel):
    consensus: str | None = None
    recommendation_mean: float | None = None
    analyst_count: int | None = None
    target_mean_price: float | None = None
    target_median_price: float | None = None
    target_high_price: float | None = None
    target_low_price: float | None = None
    current_price: float | None = None
    recent_actions: list[AnalystRatingAction] = []
    data_as_of: str | None = None


class EarningsInfo(BaseModel):
    next_earnings_date: str | None = None
    previous_earnings_date: str | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    eps_surprise: float | None = None
    eps_surprise_pct: float | None = None
    revenue_estimate: str | None = None
    revenue_actual: str | None = None
    revenue_surprise: str | None = None
    revenue_surprise_pct: float | None = None
    data_as_of: str | None = None


class CompanySnapshot(BaseModel):
    ticker: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    ceo: str | None = None
    headquarters: str | None = None
    employees: int | None = None
    market_cap: str | None = None
    revenue: str | None = None
    net_income: str | None = None
    operating_income: str | None = None
    cash: str | None = None
    total_debt: str | None = None
    website: str | None = None
    logo_url: str | None = None
    wiki_summary: str | None = None
    wiki_url: str | None = None
    data_as_of: str | None = None


# ── Private company models ────────────────────────────────────────────────────

class FundingRound(BaseModel):
    round_type: str | None = None   # "Seed", "Series A", etc.
    amount: str | None = None       # "$14.2M"
    date: str | None = None         # "2022"
    lead_investor: str | None = None


class FundingInfo(BaseModel):
    total_raised: str | None = None
    latest_round: str | None = None
    latest_amount: str | None = None
    lead_investor: str | None = None
    all_investors: list[str] = []
    rounds: list[FundingRound] = []


class GrowthSignals(BaseModel):
    employee_count: str | None = None
    employee_growth_pct: str | None = None
    employee_growth_period: str | None = None
    hiring_activity: str | None = None      # "High" | "Moderate" | "Low"
    open_positions: str | None = None
    new_locations: list[str] = []


class Milestone(BaseModel):
    year: str
    event: str


class MarketTraction(BaseModel):
    customers: list[str] = []
    partnerships: list[str] = []
    arr: str | None = None
    estimated_revenue: str | None = None
    mau: str | None = None
    enterprise_clients: list[str] = []


# ── Combined response ─────────────────────────────────────────────────────────

class MarketAnalysis(BaseModel):
    company: str
    company_type: str = "public"        # "public" | "private"
    stage: str | None = None            # private only: "Seed", "Series A", etc.
    summary: str
    market_size: str
    positioning: Positioning
    swot: SwotAnalysis
    competitors: list[Competitor]
    sources: list[Source]
    sources_count: int = 0
    confidence_score: int = 0
    financial_summary: str | None = None
    snapshot: CompanySnapshot | None = None
    social_links: SocialLinks | None = None
    recent_signals: list[RecentSignal] = []
    # Public-only fields
    financial_ratios: FinancialRatios | None = None
    analyst_sentiment: AnalystSentiment | None = None
    earnings_info: EarningsInfo | None = None
    stock_history: list[StockPoint] = []
    quarterly_earnings: list[EarningsPoint] = []
    annual_data: list[AnnualPoint] = []
    # Private-only fields
    funding: FundingInfo | None = None
    growth_signals: GrowthSignals | None = None
    milestones: list[Milestone] = []
    market_traction: MarketTraction | None = None
    investors: list[str] = []
