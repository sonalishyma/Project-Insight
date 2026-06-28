import math
import re
from datetime import date as _date
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf

# Yahoo Finance blocks default Python/yfinance user-agents on cloud IPs.
# Using a browser UA improves hit rate on hosted environments like Render.
_YF_SESSION = requests.Session()
_YF_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
})

_EXCHANGE_MAP = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE", "NYE": "NYSE",
    "PCX": "NYSE Arca",
    "BTS": "BATS",
}

# Some companies' yfinance website doesn't match their recognizable brand domain
_LOGO_DOMAIN_OVERRIDES = {
    "abc.xyz": "google.com",       # Alphabet → Google
    "meta.com": "facebook.com",    # Meta → Facebook (better logo coverage)
    "x.com": "twitter.com",        # X / Twitter
}


def _extract_domain(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").split("/")[0]


def _fmt_currency(n) -> str | None:
    try:
        n = float(n)
        if pd.isna(n):
            return None
    except (TypeError, ValueError):
        return None
    if abs(n) >= 1e12:
        return f"${n / 1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"${n / 1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"${n / 1e6:.2f}M"
    return f"${n:.2f}"


def _safe_float(val, decimals: int = 2) -> float | None:
    try:
        f = float(val)
        if pd.isna(f) or math.isinf(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def _fmt_date(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (datetime, _date)):
        return val.date().isoformat() if isinstance(val, datetime) else val.isoformat()
    try:
        return datetime.fromtimestamp(float(val)).date().isoformat()
    except (TypeError, ValueError, OSError):
        return str(val)[:10] if str(val) else None


def _fmt_grade_action(action: str | None) -> str | None:
    if not action:
        return None
    labels = {
        "up": "Upgrade",
        "down": "Downgrade",
        "main": "Maintained",
        "reit": "Reiterated",
        "init": "Initiated",
    }
    return labels.get(str(action).lower(), str(action).title())


def _find_ticker(company: str) -> str | None:
    try:
        results = yf.Search(company, max_results=5, session=_YF_SESSION)
        for q in results.quotes:
            if q.get("quoteType") == "EQUITY":
                return q.get("symbol")
        if results.quotes:
            return results.quotes[0].get("symbol")
    except Exception:
        pass
    return None


def _truncate_at_sentence(text: str, max_chars: int = 800) -> str:
    if len(text) <= max_chars:
        return text
    chunk = text[:max_chars]
    last_period = chunk.rfind(".")
    if last_period > max_chars // 2:
        return chunk[: last_period + 1]
    return chunk + "…"


import logging as _logging
_log = _logging.getLogger(__name__)


def _validate_ratios(data: dict) -> None:
    """Log warnings for values that are almost certainly unit/parsing bugs."""
    checks = [
        # (field, predicate, message)
        ("dividend_yield",    lambda v: v > 15,       "Dividend yield >15% — likely a unit bug (should be in % already)"),
        ("gross_margin",      lambda v: abs(v) > 1,   "Gross margin outside ±100% — check units (should be a fraction 0-1)"),
        ("operating_margin",  lambda v: abs(v) > 1,   "Operating margin outside ±100%"),
        ("net_margin",        lambda v: abs(v) > 2,   "Net margin outside ±200%"),
        ("pe_ratio",          lambda v: v < 0 or v > 1000, "P/E negative or >1000"),
        ("pb_ratio",          lambda v: v < 0 or v > 500,  "P/B negative or >500"),
        ("ps_ratio",          lambda v: v < 0 or v > 500,  "P/S negative or >500"),
        # NOTE: do NOT flag ROE or ROA — they legitimately exceed 100% for buyback-heavy firms
    ]
    for field, pred, msg in checks:
        val = data.get(field)
        if val is not None:
            try:
                if pred(float(val)):
                    _log.warning("[sanity] %s=%.4f: %s", field, float(val), msg)
            except (TypeError, ValueError):
                pass


def fetch(company: str) -> dict:
    result = {
        "ticker": None, "exchange": None, "sector": None, "industry": None,
        "ceo": None, "headquarters": None, "employees": None,
        "market_cap": None, "revenue": None, "net_income": None,
        "operating_income": None, "cash": None, "total_debt": None,
        "website": None, "logo_url": None,
        "pe_ratio": None, "pb_ratio": None, "ps_ratio": None, "ev_ebitda": None,
        "revenue_growth": None, "earnings_growth": None,
        "gross_margin": None, "operating_margin": None, "net_margin": None,
        "roe": None, "roa": None, "eps": None, "fcf_formatted": None,
        "debt_to_equity": None, "current_ratio": None, "quick_ratio": None,
        "dividend_yield": None,
        "wiki_summary": None, "wiki_url": None,
        "data_as_of": _date.today().isoformat(),
        "stock_history": [], "quarterly_earnings": [], "annual_data": [],
        "analyst_sentiment": None, "earnings_info": None,
    }

    ticker_sym = _find_ticker(company)
    if not ticker_sym:
        return result

    result["ticker"] = ticker_sym

    try:
        t = yf.Ticker(ticker_sym, session=_YF_SESSION)
        info = t.info or {}

        # Exchange
        raw_exchange = info.get("exchange", "")
        result["exchange"] = _EXCHANGE_MAP.get(raw_exchange, raw_exchange) or None

        # CEO
        for officer in info.get("companyOfficers", []):
            title = officer.get("title", "").lower()
            if "chief executive" in title or " ceo" in title:
                result["ceo"] = officer.get("name")
                break

        # Headquarters
        parts = [info.get("city"), info.get("state"), info.get("country")]
        hq = ", ".join(p for p in parts if p)
        result["headquarters"] = hq or None

        # Logo
        website = info.get("website", "")
        result["website"] = website or None
        if website:
            domain = _extract_domain(website).lstrip("www.")
            domain = _LOGO_DOMAIN_OVERRIDES.get(domain, domain)
            result["logo_url"] = f"https://icon.horse/icon/{domain}"

        result.update({
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "employees": info.get("fullTimeEmployees"),
            "market_cap": _fmt_currency(info.get("marketCap")),
            "revenue": _fmt_currency(info.get("totalRevenue")),
            "net_income": _fmt_currency(info.get("netIncomeToCommon")),
            "cash": _fmt_currency(info.get("totalCash")),
            "total_debt": _fmt_currency(info.get("totalDebt")),
            "pe_ratio": _safe_float(info.get("trailingPE")),
            "pb_ratio": _safe_float(info.get("priceToBook")),
            "ps_ratio": _safe_float(info.get("priceToSalesTrailing12Months")),
            "ev_ebitda": _safe_float(info.get("enterpriseToEbitda")),
            "revenue_growth": _safe_float(info.get("revenueGrowth"), 4),
            "earnings_growth": _safe_float(info.get("earningsGrowth"), 4),
            "gross_margin": _safe_float(info.get("grossMargins"), 4),
            "operating_margin": _safe_float(info.get("operatingMargins"), 4),
            "net_margin": _safe_float(info.get("profitMargins"), 4),
            "roe": _safe_float(info.get("returnOnEquity"), 4),
            "roa": _safe_float(info.get("returnOnAssets"), 4),
            "eps": _safe_float(info.get("trailingEps")),
            "fcf_formatted": _fmt_currency(info.get("freeCashflow")),
            "current_ratio": _safe_float(info.get("currentRatio")),
            "quick_ratio": _safe_float(info.get("quickRatio")),
        })

        recent_actions = []
        try:
            actions = t.upgrades_downgrades
            if actions is not None and not actions.empty:
                for idx, row in actions.head(5).iterrows():
                    recent_actions.append({
                        "date": _fmt_date(idx),
                        "firm": row.get("Firm"),
                        "action": _fmt_grade_action(row.get("Action")),
                        "from_grade": row.get("FromGrade") or None,
                        "to_grade": row.get("ToGrade") or None,
                        "current_price_target": _safe_float(row.get("currentPriceTarget")),
                        "prior_price_target": _safe_float(row.get("priorPriceTarget")),
                    })
        except Exception:
            pass

        has_analyst_data = any(info.get(k) is not None for k in [
            "recommendationKey", "recommendationMean", "targetMeanPrice",
            "targetMedianPrice", "targetHighPrice", "targetLowPrice",
            "numberOfAnalystOpinions",
        ]) or bool(recent_actions)
        if has_analyst_data:
            result["analyst_sentiment"] = {
                "consensus": str(info.get("recommendationKey")).replace("_", " ").title() if info.get("recommendationKey") else None,
                "recommendation_mean": _safe_float(info.get("recommendationMean")),
                "analyst_count": info.get("numberOfAnalystOpinions"),
                "target_mean_price": _safe_float(info.get("targetMeanPrice")),
                "target_median_price": _safe_float(info.get("targetMedianPrice")),
                "target_high_price": _safe_float(info.get("targetHighPrice")),
                "target_low_price": _safe_float(info.get("targetLowPrice")),
                "current_price": _safe_float(info.get("currentPrice")),
                "recent_actions": recent_actions,
                "data_as_of": result["data_as_of"],
            }

        try:
            cal = t.calendar or {}
        except Exception:
            cal = {}

        earnings_dates = cal.get("Earnings Date")
        next_earnings = None
        if isinstance(earnings_dates, list) and earnings_dates:
            next_earnings = _fmt_date(earnings_dates[0])
        else:
            next_earnings = _fmt_date(info.get("earningsTimestampStart") or info.get("earningsTimestamp"))

        eps_estimate = _safe_float(cal.get("Earnings Average"))
        revenue_estimate = _fmt_currency(cal.get("Revenue Average"))
        earnings_info = {
            "next_earnings_date": next_earnings,
            "previous_earnings_date": _fmt_date(info.get("earningsTimestamp")),
            "eps_estimate": eps_estimate,
            "eps_actual": None,
            "eps_surprise": None,
            "eps_surprise_pct": None,
            "revenue_estimate": revenue_estimate,
            "revenue_actual": None,
            "revenue_surprise": None,
            "revenue_surprise_pct": None,
            "data_as_of": result["data_as_of"],
        }

        try:
            dates = t.get_earnings_dates(limit=4)
            if dates is not None and not dates.empty:
                past = dates[dates.index.date <= _date.today()]
                if not past.empty:
                    row = past.iloc[0]
                    earnings_info.update({
                        "previous_earnings_date": _fmt_date(past.index[0]),
                        "eps_estimate": _safe_float(row.get("EPS Estimate")) or earnings_info["eps_estimate"],
                        "eps_actual": _safe_float(row.get("Reported EPS")),
                        "eps_surprise_pct": _safe_float(row.get("Surprise(%)"), 4),
                    })
                    if earnings_info["eps_actual"] is not None and earnings_info["eps_estimate"] is not None:
                        earnings_info["eps_surprise"] = _safe_float(earnings_info["eps_actual"] - earnings_info["eps_estimate"])
        except Exception:
            pass

        if any(v is not None for k, v in earnings_info.items() if k != "data_as_of"):
            result["earnings_info"] = earnings_info

        # Dividend yield: yfinance returns this in % form (0.38 = 0.38%), not fraction (0.0038).
        # Normalize: if the raw value looks like a fraction (< 0.20), convert to %.
        dy_raw = info.get("dividendYield")
        if dy_raw is not None:
            try:
                dy = float(dy_raw)
                if 0 < dy < 0.20:
                    dy *= 100
                result["dividend_yield"] = _safe_float(dy, 4)
            except (TypeError, ValueError):
                pass

        # Compute D/E from balance sheet rather than trusting yfinance's debtToEquity field,
        # which is documented to return the value ×100 (inconsistent with other ratios).
        try:
            qbs = t.quarterly_balance_sheet
            if qbs is not None and not qbs.empty:
                equity_rows = [
                    "Stockholders Equity",
                    "Total Stockholder Equity",
                    "Total Equity Gross Minority Interest",
                ]
                for row in equity_rows:
                    if row in qbs.index:
                        equity = float(qbs.loc[row, qbs.columns[0]])
                        if pd.isna(equity) or abs(equity) < 1e6:
                            result["debt_to_equity"] = None
                        else:
                            total_debt_raw = info.get("totalDebt")
                            if total_debt_raw:
                                result["debt_to_equity"] = _safe_float(float(total_debt_raw) / equity)
                        break
        except Exception:
            pass

        # Operating income from income statement (not directly in info)
        try:
            qi = t.quarterly_income_stmt
            if qi is not None and not qi.empty and "Operating Income" in qi.index:
                op = float(qi.loc["Operating Income", qi.columns[0]])
                result["operating_income"] = _fmt_currency(op) if not pd.isna(op) else None
        except Exception:
            pass

        # 1-year weekly stock history with OHLCV + change
        hist = t.history(period="1y", interval="1wk")
        if not hist.empty:
            stock_history = []
            prev_close = None
            for idx, row in hist.iterrows():
                close = _safe_float(row["Close"])
                if close is None:
                    continue
                change = round(close - prev_close, 2) if prev_close else 0.0
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
                stock_history.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "close": close,
                    "open": _safe_float(row.get("Open")),
                    "high": _safe_float(row.get("High")),
                    "low": _safe_float(row.get("Low")),
                    "volume": int(row["Volume"]) if row.get("Volume") and not pd.isna(row["Volume"]) else None,
                    "change": change,
                    "change_pct": change_pct,
                })
                prev_close = close
            result["stock_history"] = stock_history

        # Quarterly revenue + net income
        try:
            qi = t.quarterly_income_stmt
            if qi is not None and not qi.empty:
                has_rev = "Total Revenue" in qi.index
                has_ni = "Net Income" in qi.index
                points = []
                for col in list(qi.columns)[:8]:
                    rev = float(qi.loc["Total Revenue", col]) if has_rev else None
                    ni = float(qi.loc["Net Income", col]) if has_ni else None
                    points.append({
                        "quarter": col.strftime("%Y-%m-%d"),
                        "revenue": _safe_float(rev / 1e9) if rev is not None and not pd.isna(rev) else None,
                        "net_income": _safe_float(ni / 1e9) if ni is not None and not pd.isna(ni) else None,
                    })
                result["quarterly_earnings"] = list(reversed(points))
        except Exception:
            pass

        # Annual data from income statement + cashflow
        try:
            inc = t.income_stmt
            cf = t.cashflow
            shares = info.get("sharesOutstanding")
            if inc is not None and not inc.empty:
                annual = []
                for col in list(inc.columns)[:5]:
                    def _get(stmt, row):
                        if stmt is None or row not in stmt.index:
                            return None
                        v = stmt.loc[row, col] if col in stmt.columns else None
                        return float(v) if v is not None and not pd.isna(v) else None

                    rev = _get(inc, "Total Revenue")
                    ni = _get(inc, "Net Income")
                    gp = _get(inc, "Gross Profit")
                    op = _get(inc, "Operating Income")
                    fcf = _get(cf, "Free Cash Flow")

                    eps = None
                    if ni is not None and shares:
                        eps = _safe_float(ni / float(shares))

                    annual.append({
                        "year": str(col.year) if hasattr(col, "year") else str(col)[:4],
                        "revenue": _safe_float(rev / 1e9) if rev else None,
                        "net_income": _safe_float(ni / 1e9) if ni else None,
                        "gross_profit": _safe_float(gp / 1e9) if gp else None,
                        "operating_income": _safe_float(op / 1e9) if op else None,
                        "fcf": _safe_float(fcf / 1e9) if fcf else None,
                        "eps": eps,
                    })
                result["annual_data"] = list(reversed(annual))
        except Exception:
            pass

    except Exception:
        pass

    _validate_ratios(result)

    # Wikipedia
    try:
        import wikipediaapi
        wiki = wikipediaapi.Wikipedia(user_agent="MarketResearchTool/1.0", language="en")
        for query in [f"{company} Inc", f"{company} (company)", company]:
            page = wiki.page(query)
            if page.exists():
                result["wiki_summary"] = _truncate_at_sentence(page.summary)
                result["wiki_url"] = page.fullurl
                break
    except Exception:
        pass

    return result


def search_companies(query: str, limit: int = 6) -> list[dict]:
    """Return lightweight company suggestions for autocomplete."""
    q = query.strip()
    if len(q) < 2:
        return []
    try:
        results = yf.Search(q, max_results=limit, session=_YF_SESSION)
        suggestions = []
        seen: set[str] = set()
        for item in results.quotes:
            symbol = item.get("symbol")
            name = item.get("shortname") or item.get("longname") or item.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            suggestions.append({
                "name": name,
                "symbol": symbol,
                "exchange": item.get("exchange"),
                "quote_type": item.get("quoteType"),
            })
        return suggestions
    except Exception:
        return []


def _logo_domain(name: str, website: str) -> str:
    """Best domain to use for Clearbit logo lookup."""
    if website:
        d = _extract_domain(website).lstrip("www.")
        if d:
            return d
    # Guess from company name as fallback
    cleaned = re.sub(
        r"\s+(Inc\.?|Corp\.?|Ltd\.?|LLC|Group|Holdings?|Technologies?|Tech|Systems?|Co\.?|Platforms?|Corporation)$",
        "", name.strip(), flags=re.I,
    )
    slug = re.sub(r"[^a-z0-9]", "", cleaned.lower())
    return f"{slug}.com" if len(slug) >= 2 else ""


def enrich_competitor(comp: dict) -> dict:
    """Add ticker, market cap (USD only), revenue, industry, logo to a competitor dict."""
    name = comp.get("name", "")
    try:
        results = yf.Search(name, max_results=5, session=_YF_SESSION)
        for q in results.quotes:
            if q.get("quoteType") == "EQUITY":
                ticker_sym = q.get("symbol")
                t = yf.Ticker(ticker_sym, session=_YF_SESSION)
                try:
                    info = t.info or {}
                    currency = info.get("currency", "USD")
                    website = info.get("website", "")
                    domain = _logo_domain(name, website)
                    domain = _LOGO_DOMAIN_OVERRIDES.get(domain, domain)
                    # Only show market cap / revenue when denominated in USD
                    usd = currency == "USD"
                    return {
                        **comp,
                        "ticker": ticker_sym,
                        "market_cap": _fmt_currency(info.get("marketCap")) if usd else None,
                        "revenue": _fmt_currency(info.get("totalRevenue")) if usd else None,
                        "industry": info.get("industry"),
                        "logo_url": f"https://icon.horse/icon/{domain}" if domain else None,
                    }
                except Exception:
                    return {**comp, "ticker": ticker_sym}
    except Exception:
        pass
    return comp


def get_stock_history(ticker: str, period: str) -> list[dict]:
    """Fetch OHLCV history for a given period. Used by the /stock endpoint."""
    period_to_interval = {
        "1d": "5m", "1mo": "1d", "6mo": "1d", "1y": "1wk", "5y": "1mo",
    }
    interval = period_to_interval.get(period, "1wk")
    try:
        t = yf.Ticker(ticker, session=_YF_SESSION)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            return []
        points = []
        prev_close = None
        fmt = "%Y-%m-%d %H:%M" if period == "1d" else "%Y-%m-%d"
        for idx, row in hist.iterrows():
            close = _safe_float(row["Close"])
            if close is None:
                continue
            change = round(close - prev_close, 2) if prev_close else 0.0
            change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
            points.append({
                "date": idx.strftime(fmt),
                "close": close,
                "open": _safe_float(row.get("Open")),
                "high": _safe_float(row.get("High")),
                "low": _safe_float(row.get("Low")),
                "volume": int(row["Volume"]) if row.get("Volume") and not pd.isna(row["Volume"]) else None,
                "change": change,
                "change_pct": change_pct,
            })
            prev_close = close
        return points
    except Exception:
        return []
