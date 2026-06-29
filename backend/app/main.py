import html as _html
import os
import re

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .schemas import AnalyzeRequest, MarketAnalysis
from . import pipeline, market_data, search, social, media

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Market Research Tool")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: allow localhost in dev + the deployed frontend URL if set via env var
_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://127.0.0.1:5173",
    "https://project-insight-roan.vercel.app",
]
if os.getenv("FRONTEND_URL"):
    _origins.append(os.environ["FRONTEND_URL"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/market")
def debug_market(company: str = Query(default="Nike")):
    """Diagnostic: returns raw market data fetch result for a company name."""
    from . import edgar as _edgar
    ticker, cik = _edgar.find_ticker(company)
    mdata = market_data.fetch(company)
    return {
        "edgar_ticker": ticker,
        "edgar_cik": cik,
        "fmp_market_cap": mdata.get("market_cap"),
        "fmp_exchange": mdata.get("exchange"),
        "fmp_sector": mdata.get("sector"),
        "is_public": bool(mdata.get("ticker") and (
            mdata.get("market_cap") or mdata.get("stock_history") or mdata.get("annual_data")
        )),
        "logo_url": mdata.get("logo_url"),
        "ticker_in_result": mdata.get("ticker"),
    }


@app.post("/analyze", response_model=MarketAnalysis)
@limiter.limit("6/minute")
def analyze(request: Request, req: AnalyzeRequest):
    return pipeline.run(req.company)


@app.get("/stock/{ticker}")
@limiter.limit("30/minute")
def get_stock(request: Request, ticker: str, period: str = Query(default="1y")):
    return {"data": market_data.get_stock_history(ticker, period)}


@app.get("/companies")
@limiter.limit("60/minute")
def search_companies(request: Request, q: str = Query(..., min_length=2, max_length=80)):
    return {"suggestions": market_data.search_companies(q)}


@app.get("/news/{company}")
@limiter.limit("20/minute")
def get_news(request: Request, company: str, ticker: str = Query(default=None)):
    """Return recent news, merging Tavily search with yfinance news when ticker is known."""
    tavily_articles = search.fetch_news(company, days=30)

    yf_articles: list[dict] = []
    if ticker:
        yf_articles = market_data.get_yf_news(ticker)

    # Merge and deduplicate by URL, then sort newest-first
    seen: set[str] = {a["url"] for a in tavily_articles}
    for a in yf_articles:
        if a["url"] not in seen:
            tavily_articles.append(a)
            seen.add(a["url"])

    tavily_articles.sort(key=lambda a: a.get("date") or "", reverse=True)
    return {"articles": tavily_articles}


@app.get("/social/{ticker}")
@limiter.limit("30/minute")
def get_social(request: Request, ticker: str):
    """Return StockTwits social sentiment for a stock ticker."""
    return social.fetch_stocktwits(ticker)


@app.get("/media/{company}")
@limiter.limit("10/minute")
def get_media(request: Request, company: str):
    """
    Return Media & Public Opinion data: HN posts, Reddit posts,
    source registry with formatted search URLs, and coverage mapping
    from any articles already found for this company.
    """
    return media.fetch_media_overview(company)


@app.get("/preview")
@limiter.limit("60/minute")
async def preview_url(request: Request, url: str = Query(...)):
    """Return OG image + description for a URL (used by source cards)."""
    try:
        async with httpx.AsyncClient(
            timeout=6.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MarketBot/1.0)"},
        ) as client:
            r = await client.get(url)
            html = r.text[:40000]

        def og(tag: str) -> str | None:
            m = (
                re.search(
                    rf'<meta[^>]+property=["\']og:{tag}["\'][^>]+content=["\']([^"\']+)',
                    html, re.I,
                ) or re.search(
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:{tag}["\']',
                    html, re.I,
                )
            )
            return m.group(1) if m else None

        img = og("image")
        return {"image": _html.unescape(img) if img else None, "description": og("description")}
    except Exception:
        return {"image": None, "description": None}
