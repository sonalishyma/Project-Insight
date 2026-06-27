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
from . import pipeline, market_data, search

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
def get_news(request: Request, company: str):
    return {"articles": search.fetch_news(company)}


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
