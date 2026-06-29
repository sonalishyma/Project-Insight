import math
import os
import re
from datetime import date as _date
from concurrent.futures import ThreadPoolExecutor

import httpx

_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_FMP_BASE = "https://financialmodelingprep.com/stable"

_EXCHANGE_MAP = {
    "NASDAQ": "NASDAQ", "NYSE": "NYSE", "AMEX": "AMEX",
    "NYSE ARCA": "NYSE Arca", "BATS": "BATS",
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NYQ": "NYSE",
    "NCM": "NASDAQ", "NasdaqGS": "NASDAQ", "NasdaqGM": "NASDAQ", "NasdaqCM": "NASDAQ",
}

_LOGO_DOMAIN_OVERRIDES = {
    "abc.xyz": "google.com",
    "meta.com": "facebook.com",
    "x.com": "twitter.com",
}

_client = httpx.Client(timeout=12.0, headers={"User-Agent": "Insight/1.0"})


def _fmp(path: str, _p: dict | None = None, **kwargs):
    """Call FMP API (used only for /profile — 1 call per company)."""
    if not _FMP_KEY:
        return None
    try:
        params = {**(_p or {}), **kwargs, "apikey": _FMP_KEY}
        r = _client.get(f"{_FMP_BASE}{path}", params=params)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and ("Error Message" in data or data.get("status") == "LIMIT_REACH"):
            return None
        return data if data else None
    except Exception:
        return None


def _fmt_currency(n) -> str | None:
    try:
        n = float(n)
        if math.isnan(n) or math.isinf(n):
            return None
    except (TypeError, ValueError):
        return None
    abs_n = abs(n)
    if abs_n >= 1e12:
        return f"${n / 1e12:.2f}T"
    if abs_n >= 1e9:
        return f"${n / 1e9:.2f}B"
    if abs_n >= 1e6:
        return f"${n / 1e6:.2f}M"
    return f"${n:.2f}"


def _safe_float(val, decimals: int = 2) -> float | None:
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def _extract_domain(url: str) -> str:
    host = url.replace("https://", "").replace("http://", "").split("/")[0]
    host = re.sub(r"^(www|investors?|ir|about|corporate|finance|investor|careers|news)\.", "", host)
    return host


def _truncate_at_sentence(text: str, max_chars: int = 800) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    chunk = text[:max_chars]
    last_period = chunk.rfind(".")
    if last_period > max_chars // 2:
        return chunk[: last_period + 1]
    return chunk + "…"


def _yf_search_ticker(company: str) -> str | None:
    """
    Search Yahoo Finance for the best-matching public company ticker.
    Fallback when EDGAR doesn't have the company (handles subsidiaries,
    brand names, international ADRs, and recent IPOs).
    """
    # Try yfinance Search class first
    try:
        import yfinance as yf
        results = yf.Search(company, news_count=0, max_results=5)
        quotes = getattr(results, "quotes", None) or []
        for q in quotes:
            sym = q.get("symbol", "")
            exch = q.get("exchDisp", "")
            # Accept US-listed equities; reject mutual funds, crypto, ADRs with dots
            if (q.get("quoteType") == "EQUITY"
                    and "." not in sym
                    and len(sym) <= 6
                    and (exch in ("NYSE", "NASDAQ", "AMEX", "NasdaqGS", "NasdaqGM", "NYSEArca")
                         or "OTC" in exch or "Pink" in exch)):
                print(f"[yf_search] '{company}' → {sym} ({q.get('shortname')})", flush=True)
                return sym
    except Exception as e:
        print(f"[yf_search] yf.Search failed for '{company}': {e}", flush=True)

    # Fallback: direct Yahoo Finance query API (no rate limit, no key)
    try:
        r = _client.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": company, "quotesCount": 5, "newsCount": 0, "listsCount": 0},
        )
        for q in r.json().get("quotes", []):
            sym = q.get("symbol", "")
            if q.get("quoteType") == "EQUITY" and "." not in sym and len(sym) <= 5:
                print(f"[yf_search_api] '{company}' → {sym} ({q.get('shortname')})", flush=True)
                return sym
    except Exception as e:
        print(f"[yf_search_api] failed for '{company}': {e}", flush=True)

    return None


def _yf_val(df, row_name: str, col):
    """Safely extract a float from a yfinance DataFrame cell."""
    if row_name not in df.index:
        return None
    v = df.at[row_name, col]
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _yf_fetch(ticker_sym: str) -> dict:
    """
    Fetch comprehensive financial data from Yahoo Finance via yfinance.
    No API key required, no rate limits.
    """
    try:
        import yfinance as yf
    except ImportError:
        print(f"[yf] yfinance not installed", flush=True)
        return {}

    out: dict = {}
    yt = yf.Ticker(ticker_sym)

    # ── Company info + ratios (single HTTP call) ─────────────────────────────
    try:
        info = yt.info or {}
        if not info:
            print(f"[yf] empty info for {ticker_sym}", flush=True)

        officers = info.get("companyOfficers") or []
        ceo = next(
            (o.get("name") for o in officers if "CEO" in (o.get("title") or "").upper()),
            officers[0].get("name") if officers else None,
        )

        website = info.get("website") or ""
        domain = _extract_domain(website) if website else ""
        domain = _LOGO_DOMAIN_OVERRIDES.get(domain, domain)
        exchange_raw = info.get("exchange") or info.get("fullExchangeName") or ""
        hq = ", ".join(x for x in [info.get("city"), info.get("state"), info.get("country")] if x)
        raw_dy = info.get("dividendYield")

        out.update({
            "company_name": info.get("longName") or info.get("shortName"),
            "exchange": _EXCHANGE_MAP.get(exchange_raw, exchange_raw) or None,
            "sector": info.get("sector") or None,
            "industry": info.get("industry") or None,
            "ceo": ceo,
            "headquarters": hq or None,
            "employees": info.get("fullTimeEmployees"),
            "market_cap": _fmt_currency(info.get("marketCap")),
            "revenue": _fmt_currency(info.get("totalRevenue")),
            "net_income": _fmt_currency(info.get("netIncomeToCommon")),
            "website": website or None,
            "logo_url": f"https://icon.horse/icon/{domain}" if domain else None,
            "wiki_summary": _truncate_at_sentence(info.get("longBusinessSummary") or "") or None,
            # Valuation
            "pe_ratio": _safe_float(info.get("trailingPE")),
            "pb_ratio": _safe_float(info.get("priceToBook")),
            "ps_ratio": _safe_float(info.get("priceToSalesTrailing12Months")),
            "ev_ebitda": _safe_float(info.get("enterpriseToEbitda")),
            # Profitability
            "gross_margin": _safe_float(info.get("grossMargins"), 4),
            "operating_margin": _safe_float(info.get("operatingMargins"), 4),
            "net_margin": _safe_float(info.get("profitMargins"), 4),
            "roe": _safe_float(info.get("returnOnEquity"), 4),
            "roa": _safe_float(info.get("returnOnAssets"), 4),
            # Growth
            "revenue_growth": _safe_float(info.get("revenueGrowth"), 4),
            "earnings_growth": _safe_float(info.get("earningsGrowth"), 4),
            # Per share & liquidity
            "eps": _safe_float(info.get("trailingEps")),
            "cash": _fmt_currency(info.get("totalCash")),
            "total_debt": _fmt_currency(info.get("totalDebt")),
            "fcf_formatted": _fmt_currency(info.get("freeCashflow")),
            "current_ratio": _safe_float(info.get("currentRatio")),
            "quick_ratio": _safe_float(info.get("quickRatio")),
            "debt_to_equity": _safe_float(info.get("debtToEquity")),
            "dividend_yield": _safe_float(float(raw_dy) * 100, 4) if raw_dy else None,
        })

        if info.get("targetMeanPrice") or info.get("numberOfAnalystOpinions"):
            out["analyst_sentiment"] = {
                "consensus": info.get("recommendationKey"),
                "recommendation_mean": _safe_float(info.get("recommendationMean")),
                "analyst_count": info.get("numberOfAnalystOpinions"),
                "target_mean_price": _safe_float(info.get("targetMeanPrice")),
                "target_median_price": _safe_float(info.get("targetMedianPrice")),
                "target_high_price": _safe_float(info.get("targetHighPrice")),
                "target_low_price": _safe_float(info.get("targetLowPrice")),
                "current_price": _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
                "recent_actions": [],
                "data_as_of": _date.today().isoformat(),
            }
    except Exception as e:
        print(f"[yf] info failed for {ticker_sym}: {e}", flush=True)

    # ── Stock price history ──────────────────────────────────────────────────
    try:
        hist = yt.history(period="1y", auto_adjust=True)
        if hist is not None and not hist.empty:
            hist_reset = hist.reset_index()
            sampled = hist_reset.iloc[::5]
            stock_history = []
            prev_close = None
            for _, row in sampled.iterrows():
                close = _safe_float(row.get("Close"))
                if close is None:
                    continue
                change = round(close - prev_close, 2) if prev_close else 0.0
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
                date_val = row.get("Date") or row.get("Datetime")
                date_str = str(date_val.date()) if hasattr(date_val, "date") else str(date_val)[:10]
                stock_history.append({
                    "date": date_str,
                    "close": close,
                    "open": _safe_float(row.get("Open")),
                    "high": _safe_float(row.get("High")),
                    "low": _safe_float(row.get("Low")),
                    "volume": int(row["Volume"]) if row.get("Volume") else None,
                    "change": change,
                    "change_pct": change_pct,
                })
                prev_close = close
            out["stock_history"] = stock_history
    except Exception as e:
        print(f"[yf] history failed for {ticker_sym}: {e}", flush=True)

    # ── Annual income statement ──────────────────────────────────────────────
    try:
        inc = yt.income_stmt
        if inc is not None and not inc.empty:
            cols = list(inc.columns)  # newest → oldest
            annual_data = []
            for col in reversed(cols):  # oldest → newest for chart
                rev  = _yf_val(inc, "Total Revenue", col)
                ni   = _yf_val(inc, "Net Income", col)
                gp   = _yf_val(inc, "Gross Profit", col)
                op   = _yf_val(inc, "Operating Income", col)
                eps  = _yf_val(inc, "Diluted EPS", col)
                annual_data.append({
                    "year": str(col)[:4],
                    "revenue":          _safe_float(rev / 1e9) if rev else None,
                    "net_income":       _safe_float(ni  / 1e9) if ni  else None,
                    "gross_profit":     _safe_float(gp  / 1e9) if gp  else None,
                    "operating_income": _safe_float(op  / 1e9) if op  else None,
                    "fcf": None,
                    "eps": _safe_float(eps) if eps else None,
                })
            out["annual_data"] = annual_data

            if len(cols) >= 2 and not out.get("revenue_growth"):
                r0 = _yf_val(inc, "Total Revenue", cols[0])
                r1 = _yf_val(inc, "Total Revenue", cols[1])
                if r0 and r1 and r1 > 0:
                    out["revenue_growth"] = _safe_float((r0 - r1) / r1, 4)

            if not out.get("eps"):
                eps_latest = _yf_val(inc, "Diluted EPS", cols[0]) if cols else None
                if eps_latest:
                    out["eps"] = _safe_float(eps_latest)

            if not out.get("net_income"):
                ni_latest = _yf_val(inc, "Net Income", cols[0]) if cols else None
                out["net_income"] = _fmt_currency(ni_latest)
    except Exception as e:
        print(f"[yf] income_stmt failed for {ticker_sym}: {e}", flush=True)

    # ── Quarterly earnings ───────────────────────────────────────────────────
    try:
        inc_q = yt.quarterly_income_stmt
        if inc_q is not None and not inc_q.empty:
            cols_q = list(inc_q.columns)
            points = []
            for col in reversed(cols_q[-8:]):
                rev = _yf_val(inc_q, "Total Revenue", col)
                ni  = _yf_val(inc_q, "Net Income", col)
                points.append({
                    "quarter": str(col)[:10],
                    "revenue":    _safe_float(rev / 1e9) if rev else None,
                    "net_income": _safe_float(ni  / 1e9) if ni  else None,
                })
            out["quarterly_earnings"] = points
    except Exception as e:
        print(f"[yf] quarterly_income_stmt failed for {ticker_sym}: {e}", flush=True)

    # ── Cash flow (FCF for annual chart) ────────────────────────────────────
    try:
        cf = yt.cashflow
        if cf is not None and not cf.empty:
            cols_cf = list(cf.columns)
            fcf_latest = _yf_val(cf, "Free Cash Flow", cols_cf[0]) if cols_cf else None
            if fcf_latest and not out.get("fcf_formatted"):
                out["fcf_formatted"] = _fmt_currency(fcf_latest)
            # Patch FCF into annual_data
            fcf_by_year = {}
            for col in cols_cf:
                fcf = _yf_val(cf, "Free Cash Flow", col)
                if fcf is not None:
                    fcf_by_year[str(col)[:4]] = _safe_float(fcf / 1e9)
            if out.get("annual_data") and fcf_by_year:
                for pt in out["annual_data"]:
                    pt["fcf"] = fcf_by_year.get(pt["year"])
    except Exception as e:
        print(f"[yf] cashflow failed for {ticker_sym}: {e}", flush=True)

    print(f"[yf] fetched {ticker_sym}: market_cap={out.get('market_cap')}, history_pts={len(out.get('stock_history', []))}", flush=True)
    return out


def fetch(company: str) -> dict:
    result: dict = {
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
        "cik": None, "company_name": None,
    }

    from . import edgar as _edgar
    ticker_sym, edgar_cik = _edgar.find_ticker(company)
    print(f"[market_data] EDGAR lookup for '{company}': {ticker_sym}", flush=True)

    if not ticker_sym:
        # EDGAR didn't find it. Try Yahoo Finance search — handles brand names
        # (e.g. "Hydro Flask" → Helen of Troy), subsidiaries, international ADRs,
        # and recently IPO'd companies not yet in EDGAR's static company list.
        ticker_sym = _yf_search_ticker(company)
        edgar_cik = None  # CIK not known for YF-search results

    if not ticker_sym:
        return result  # Genuinely private or unrecognizable

    result["ticker"] = ticker_sym
    result["cik"] = edgar_cik

    # ── Primary: Yahoo Finance (no rate limits, covers all listed stocks) ──
    yf_data = _yf_fetch(ticker_sym)
    for k, v in yf_data.items():
        if v is not None:
            result[k] = v

    # ── Enhancement: FMP /profile (1 call only) ────────────────────────────
    # Used to fill gaps (better CEO data, description from FMP if yf blank)
    # and as the source-of-truth for market_cap / is_public check.
    profile_raw = _fmp("/profile", symbol=ticker_sym)
    if isinstance(profile_raw, list) and profile_raw:
        p = profile_raw[0]
    elif isinstance(profile_raw, dict) and profile_raw:
        p = profile_raw
    else:
        p = None

    if p:
        website = p.get("website") or ""
        domain = _extract_domain(website) if website else ""
        domain = _LOGO_DOMAIN_OVERRIDES.get(domain, domain)
        hq = ", ".join(x for x in [p.get("city"), p.get("state"), p.get("country")] if x)
        emp_raw = p.get("fullTimeEmployees")
        # Only fill gaps — yfinance data wins if already set
        if not result.get("company_name"):
            result["company_name"] = p.get("companyName") or None
        if not result.get("ceo"):
            result["ceo"] = p.get("ceo") or None
        if not result.get("exchange"):
            result["exchange"] = p.get("exchange") or None
        if not result.get("sector"):
            result["sector"] = p.get("sector") or None
        if not result.get("industry"):
            result["industry"] = p.get("industry") or None
        if not result.get("headquarters"):
            result["headquarters"] = hq or None
        if not result.get("employees") and emp_raw:
            result["employees"] = int(emp_raw)
        if not result.get("market_cap"):
            result["market_cap"] = _fmt_currency(p.get("marketCap"))
        if not result.get("revenue"):
            result["revenue"] = _fmt_currency(p.get("revenue"))
        if not result.get("website"):
            result["website"] = website or None
        if not result.get("logo_url") and domain:
            result["logo_url"] = f"https://icon.horse/icon/{domain}"
        if not result.get("wiki_summary"):
            result["wiki_summary"] = _truncate_at_sentence(p.get("description") or "") or None
        result["cik"] = result.get("cik") or p.get("cik") or None

    print(f"[market_data] final: ticker={result['ticker']}, market_cap={result['market_cap']}, history_pts={len(result['stock_history'])}", flush=True)
    return result


def search_companies(query: str, limit: int = 6) -> list[dict]:
    q = query.strip()
    if len(q) < 2:
        return []
    data = _fmp("/search", query=q, limit=limit) or []
    suggestions = []
    seen: set[str] = set()
    for item in data:
        name = item.get("name") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        suggestions.append({
            "name": name,
            "symbol": item.get("symbol"),
            "exchange": item.get("exchangeShortName"),
            "quote_type": "EQUITY" if item.get("exchangeShortName") else None,
        })
    return suggestions


_LOGO_SKIP_WORDS = {
    'inc', 'corp', 'ltd', 'llc', 'co', 'plc', 'group', 'the', 'holding', 'holdings',
    'technologies', 'technology', 'tech', 'electronics', 'corporation', 'company',
    'international', 'global', 'systems', 'solutions', 'services', 'industries',
    'enterprises', 'partners', 'ventures',
}

def _guess_logo(name: str) -> str | None:
    """icon.horse URL derived from the first meaningful word of a company name."""
    clean = re.sub(r'\s*\([^)]*\)', '', name)
    words = [w for w in re.sub(r'[^\w\s]', '', clean).lower().split()
             if w not in _LOGO_SKIP_WORDS]
    slug = words[0] if words else ''
    return f"https://icon.horse/icon/{slug}.com" if len(slug) >= 2 else None


def enrich_competitor(comp: dict) -> dict:
    if not isinstance(comp, dict):
        return {"name": str(comp), "note": "", "overlapping_products": []}
    name = comp.get("name", "")
    if not name:
        return comp

    clean_name = re.sub(r'\s*\([^)]*\)', '', name).strip()

    from . import edgar as _edgar
    ticker_sym, _ = _edgar.find_ticker(clean_name)
    if not ticker_sym:
        return {**comp, "logo_url": _guess_logo(name)}

    profile_raw = _fmp("/profile", symbol=ticker_sym)
    if isinstance(profile_raw, list) and profile_raw:
        p = profile_raw[0]
    elif isinstance(profile_raw, dict) and profile_raw:
        p = profile_raw
    else:
        return {**comp, "ticker": ticker_sym, "logo_url": _guess_logo(name)}

    website = p.get("website") or ""
    domain = _extract_domain(website) if website else ""
    domain = _LOGO_DOMAIN_OVERRIDES.get(domain, domain)
    return {
        **comp,
        "ticker": ticker_sym,
        "market_cap": _fmt_currency(p.get("marketCap")),
        "revenue": _fmt_currency(p.get("revenue")),
        "industry": p.get("industry"),
        "logo_url": f"https://icon.horse/icon/{domain}" if domain else _guess_logo(name),
    }


def get_stock_history(ticker: str, period: str) -> list[dict]:
    """Fetch stock price history via yfinance (with FMP fallback)."""
    yf_period_map = {"1d": "1d", "1mo": "1mo", "6mo": "6mo", "1y": "1y", "5y": "5y"}
    interval_map  = {"1d": "5m", "1mo": "1d", "6mo": "1d", "1y": "1d", "5y": "1wk"}
    sample_map    = {"1d": 1,   "1mo": 1,    "6mo": 1,    "1y": 5,   "5y": 1}

    yf_period = yf_period_map.get(period, "1y")
    interval  = interval_map.get(period, "1d")
    sample    = sample_map.get(period, 5)

    try:
        import yfinance as yf
        yt = yf.Ticker(ticker)
        hist = yt.history(period=yf_period, interval=interval, auto_adjust=True)
        if hist is not None and not hist.empty:
            hist_reset = hist.reset_index()
            sampled = hist_reset.iloc[::sample]
            points = []
            prev_close = None
            for _, row in sampled.iterrows():
                close = _safe_float(row.get("Close"))
                if close is None:
                    continue
                change = round(close - prev_close, 2) if prev_close else 0.0
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
                date_val = row.get("Datetime") or row.get("Date")
                if period == "1d":
                    date_str = str(date_val) if date_val is not None else ""
                else:
                    date_str = str(date_val.date()) if hasattr(date_val, "date") else str(date_val)[:10]
                points.append({
                    "date": date_str,
                    "close": close,
                    "open": _safe_float(row.get("Open")),
                    "high": _safe_float(row.get("High")),
                    "low": _safe_float(row.get("Low")),
                    "volume": int(row["Volume"]) if row.get("Volume") else None,
                    "change": change,
                    "change_pct": change_pct,
                })
                prev_close = close
            if points:
                return points
    except Exception as e:
        print(f"[yf] get_stock_history failed for {ticker}/{period}: {e}", flush=True)

    # FMP fallback (in case yfinance is unavailable)
    period_timeseries = {"1d": 2, "1mo": 30, "6mo": 180, "1y": 365, "5y": 1825}
    period_sample     = {"1d": 1, "1mo": 1,  "6mo": 3,   "1y": 5,   "5y": 20}
    ts = period_timeseries.get(period, 365)
    samp = period_sample.get(period, 5)

    if period == "1d":
        data = _fmp("/historical-chart/5min", symbol=ticker) or []
        points = []
        for pt in list(reversed(data))[-80:]:
            close = _safe_float(pt.get("close"))
            if close is None:
                continue
            points.append({
                "date": str(pt.get("date", "")),
                "close": close, "open": _safe_float(pt.get("open")),
                "high": _safe_float(pt.get("high")), "low": _safe_float(pt.get("low")),
                "volume": int(pt["volume"]) if pt.get("volume") else None,
                "change": 0.0, "change_pct": 0.0,
            })
        return points

    hist = _fmp("/historical-price-eod/full", symbol=ticker, timeseries=ts)
    raw = hist.get("historical") if isinstance(hist, dict) else (hist if isinstance(hist, list) else [])
    daily = list(reversed(raw or []))
    sampled = daily[::samp]
    points = []
    prev_close = None
    for pt in sampled:
        close = _safe_float(pt.get("close"))
        if close is None:
            continue
        change = round(close - prev_close, 2) if prev_close else 0.0
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
        points.append({
            "date": str(pt.get("date", ""))[:10],
            "close": close, "open": _safe_float(pt.get("open")),
            "high": _safe_float(pt.get("high")), "low": _safe_float(pt.get("low")),
            "volume": int(pt["volume"]) if pt.get("volume") else None,
            "change": change, "change_pct": change_pct,
        })
        prev_close = close
    return points
