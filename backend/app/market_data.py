import math
import os
import re
from datetime import date as _date, timedelta

import httpx

_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_FMP_BASE = "https://financialmodelingprep.com/api"

_EXCHANGE_MAP = {
    "NASDAQ": "NASDAQ", "NYSE": "NYSE", "AMEX": "AMEX",
    "NYSE ARCA": "NYSE Arca", "BATS": "BATS",
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NYQ": "NYSE",
}

_LOGO_DOMAIN_OVERRIDES = {
    "abc.xyz": "google.com",
    "meta.com": "facebook.com",
    "x.com": "twitter.com",
}

_client = httpx.Client(timeout=12.0, headers={"User-Agent": "Insight/1.0"})


def _fmp(path: str, _p: dict | None = None, **kwargs):
    """Call FMP API. Use _p dict for params that clash with Python keywords (e.g. 'from')."""
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
    return url.replace("https://", "").replace("http://", "").split("/")[0]


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


def _find_ticker(company: str) -> str | None:
    data = _fmp("/v3/search", query=company, limit=8)
    if not isinstance(data, list) or not data:
        return None
    priority = {"NASDAQ", "NYSE", "AMEX", "NYSE ARCA"}
    for item in data:
        if item.get("exchangeShortName") in priority:
            return item["symbol"]
    return data[0]["symbol"]


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
        "cik": None,
    }

    ticker_sym = _find_ticker(company)
    if not ticker_sym:
        return result
    result["ticker"] = ticker_sym

    # ── Company profile ────────────────────────────────────────────────────
    profile_list = _fmp(f"/v3/profile/{ticker_sym}")
    if isinstance(profile_list, list) and profile_list:
        p = profile_list[0]
        website = p.get("website") or ""
        domain = _extract_domain(website).lstrip("www.") if website else ""
        domain = _LOGO_DOMAIN_OVERRIDES.get(domain, domain)
        hq = ", ".join(x for x in [p.get("city"), p.get("state"), p.get("country")] if x)
        result.update({
            "exchange": _EXCHANGE_MAP.get(p.get("exchangeShortName", ""), p.get("exchangeShortName")) or None,
            "sector": p.get("sector") or None,
            "industry": p.get("industry") or None,
            "ceo": p.get("ceo") or None,
            "headquarters": hq or None,
            "employees": p.get("fullTimeEmployees") or None,
            "market_cap": _fmt_currency(p.get("mktCap")),
            "revenue": _fmt_currency(p.get("revenue")),
            "pe_ratio": _safe_float(p.get("pe")),
            "eps": _safe_float(p.get("eps")),
            "website": website or None,
            "logo_url": f"https://icon.horse/icon/{domain}" if domain else None,
            "wiki_summary": _truncate_at_sentence(p.get("description") or "") or None,
            "cik": p.get("cik") or None,
        })

    # ── TTM ratios ─────────────────────────────────────────────────────────
    ratios_list = _fmp(f"/v3/ratios-ttm/{ticker_sym}")
    if isinstance(ratios_list, list) and ratios_list:
        r = ratios_list[0]
        raw_dy = r.get("dividendYieldTTM")
        dy = _safe_float(float(raw_dy) * 100, 4) if raw_dy else None
        result.update({
            "pb_ratio": _safe_float(r.get("priceToBookRatioTTM")),
            "ps_ratio": _safe_float(r.get("priceToSalesRatioTTM")),
            "ev_ebitda": _safe_float(r.get("enterpriseValueMultipleTTM")),
            "gross_margin": _safe_float(r.get("grossProfitMarginTTM"), 4),
            "operating_margin": _safe_float(r.get("operatingProfitMarginTTM"), 4),
            "net_margin": _safe_float(r.get("netProfitMarginTTM"), 4),
            "roe": _safe_float(r.get("returnOnEquityTTM"), 4),
            "roa": _safe_float(r.get("returnOnAssetsTTM"), 4),
            "current_ratio": _safe_float(r.get("currentRatioTTM")),
            "quick_ratio": _safe_float(r.get("quickRatioTTM")),
            "debt_to_equity": _safe_float(r.get("debtEquityRatioTTM")),
            "dividend_yield": dy,
        })

    # ── Annual income statement ────────────────────────────────────────────
    inc_annual = _fmp(f"/v3/income-statement/{ticker_sym}", period="annual", limit=5) or []

    if inc_annual:
        latest = inc_annual[0]
        result["revenue"] = result["revenue"] or _fmt_currency(latest.get("revenue"))
        result["net_income"] = _fmt_currency(latest.get("netIncome"))
        result["operating_income"] = _fmt_currency(latest.get("operatingIncome"))
        result["eps"] = result["eps"] or _safe_float(latest.get("eps"))

        if len(inc_annual) >= 2:
            r0 = float(inc_annual[0].get("revenue") or 0)
            r1 = float(inc_annual[1].get("revenue") or 0)
            if r1 > 0:
                result["revenue_growth"] = _safe_float((r0 - r1) / r1, 4)
            e0 = float(inc_annual[0].get("eps") or 0)
            e1 = float(inc_annual[1].get("eps") or 0)
            if e1 != 0:
                result["earnings_growth"] = _safe_float((e0 - e1) / abs(e1), 4)

    # ── Annual cash flow ───────────────────────────────────────────────────
    cf_annual = _fmp(f"/v3/cash-flow-statement/{ticker_sym}", period="annual", limit=5) or []
    cf_by_year: dict[str, float | None] = {}
    for c in cf_annual:
        year = str(c.get("date", ""))[:4]
        fcf = c.get("freeCashFlow")
        cf_by_year[year] = _safe_float(float(fcf) / 1e9) if fcf is not None else None

    if cf_annual:
        latest_cf = cf_annual[0]
        result["cash"] = _fmt_currency(latest_cf.get("cashAndCashEquivalents"))
        result["fcf_formatted"] = _fmt_currency(latest_cf.get("freeCashFlow"))

    # ── Balance sheet ──────────────────────────────────────────────────────
    bs_list = _fmp(f"/v3/balance-sheet-statement/{ticker_sym}", period="annual", limit=1)
    if isinstance(bs_list, list) and bs_list:
        bs = bs_list[0]
        result["total_debt"] = _fmt_currency(bs.get("totalDebt"))
        result["cash"] = result["cash"] or _fmt_currency(bs.get("cashAndCashEquivalents"))

    # ── Annual chart data ──────────────────────────────────────────────────
    if inc_annual:
        annual_data = []
        for item in reversed(inc_annual):
            year = str(item.get("date", ""))[:4]
            rev = item.get("revenue")
            ni = item.get("netIncome")
            gp = item.get("grossProfit")
            op = item.get("operatingIncome")
            annual_data.append({
                "year": year,
                "revenue": _safe_float(float(rev) / 1e9) if rev else None,
                "net_income": _safe_float(float(ni) / 1e9) if ni else None,
                "gross_profit": _safe_float(float(gp) / 1e9) if gp else None,
                "operating_income": _safe_float(float(op) / 1e9) if op else None,
                "fcf": cf_by_year.get(year),
                "eps": _safe_float(item.get("eps")),
            })
        result["annual_data"] = annual_data

    # ── Quarterly earnings ─────────────────────────────────────────────────
    inc_q = _fmp(f"/v3/income-statement/{ticker_sym}", period="quarter", limit=8) or []
    if inc_q:
        points = []
        for item in reversed(inc_q):
            rev = item.get("revenue")
            ni = item.get("netIncome")
            points.append({
                "quarter": str(item.get("date", ""))[:10],
                "revenue": _safe_float(float(rev) / 1e9) if rev else None,
                "net_income": _safe_float(float(ni) / 1e9) if ni else None,
            })
        result["quarterly_earnings"] = points

    # ── Stock history (daily → sampled weekly) ─────────────────────────────
    # timeseries=365 avoids the 'from' Python-keyword clash in params
    hist = _fmp(f"/v3/historical-price-full/{ticker_sym}", timeseries=365)
    if isinstance(hist, dict) and hist.get("historical"):
        daily = list(reversed(hist["historical"]))  # oldest → newest
        sampled = daily[::5]                         # ~weekly resolution
        stock_history = []
        prev_close = None
        for pt in sampled:
            close = _safe_float(pt.get("close"))
            if close is None:
                continue
            change = round(close - prev_close, 2) if prev_close else 0.0
            change_pct = round((change / prev_close) * 100, 2) if prev_close else 0.0
            stock_history.append({
                "date": str(pt.get("date", ""))[:10],
                "close": close,
                "open": _safe_float(pt.get("open")),
                "high": _safe_float(pt.get("high")),
                "low": _safe_float(pt.get("low")),
                "volume": int(pt["volume"]) if pt.get("volume") else None,
                "change": change,
                "change_pct": change_pct,
            })
            prev_close = close
        result["stock_history"] = stock_history

    # ── Analyst price targets ──────────────────────────────────────────────
    try:
        consensus = _fmp("/v4/price-target-consensus", symbol=ticker_sym)
        recs = _fmp(f"/v3/analyst-stock-recommendations/{ticker_sym}", limit=10) or []
        recent_actions = [
            {
                "date": str(rec.get("date", ""))[:10],
                "firm": rec.get("analystName") or rec.get("analyst") or None,
                "action": "Maintained",
                "from_grade": None,
                "to_grade": rec.get("rating") or None,
                "current_price_target": _safe_float(rec.get("priceTarget")),
                "prior_price_target": None,
            }
            for rec in recs[:5]
        ]
        if isinstance(consensus, dict) and consensus or recent_actions:
            c = consensus if isinstance(consensus, dict) else {}
            result["analyst_sentiment"] = {
                "consensus": None,
                "recommendation_mean": None,
                "analyst_count": len(recs) or None,
                "target_mean_price": _safe_float(c.get("targetConsensus")),
                "target_median_price": _safe_float(c.get("targetMedian")),
                "target_high_price": _safe_float(c.get("targetHigh")),
                "target_low_price": _safe_float(c.get("targetLow")),
                "current_price": None,
                "recent_actions": recent_actions,
                "data_as_of": result["data_as_of"],
            }
    except Exception:
        pass

    # ── Earnings surprises ─────────────────────────────────────────────────
    try:
        surprises = _fmp(f"/v3/earnings-surprises/{ticker_sym}") or []
        if isinstance(surprises, list) and surprises:
            s = surprises[0]
            est = _safe_float(s.get("estimatedEps"))
            act = _safe_float(s.get("actualEps"))
            surprise = _safe_float(float(act) - float(est)) if act is not None and est is not None else None
            result["earnings_info"] = {
                "next_earnings_date": None,
                "previous_earnings_date": str(s.get("date", ""))[:10] or None,
                "eps_estimate": est,
                "eps_actual": act,
                "eps_surprise": surprise,
                "eps_surprise_pct": _safe_float(s.get("epsSurpriseDifference")),
                "revenue_estimate": None,
                "revenue_actual": None,
                "revenue_surprise": None,
                "revenue_surprise_pct": None,
                "data_as_of": result["data_as_of"],
            }
    except Exception:
        pass

    return result


def search_companies(query: str, limit: int = 6) -> list[dict]:
    q = query.strip()
    if len(q) < 2:
        return []
    data = _fmp("/v3/search", query=q, limit=limit) or []
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


def enrich_competitor(comp: dict) -> dict:
    name = comp.get("name", "")
    data = _fmp("/v3/search", query=name, limit=5) or []
    for item in data:
        if item.get("exchangeShortName") in {"NASDAQ", "NYSE", "AMEX"}:
            ticker_sym = item["symbol"]
            profile = _fmp(f"/v3/profile/{ticker_sym}")
            if isinstance(profile, list) and profile:
                p = profile[0]
                website = p.get("website") or ""
                domain = _extract_domain(website).lstrip("www.") if website else ""
                domain = _LOGO_DOMAIN_OVERRIDES.get(domain, domain)
                return {
                    **comp,
                    "ticker": ticker_sym,
                    "market_cap": _fmt_currency(p.get("mktCap")),
                    "revenue": _fmt_currency(p.get("revenue")),
                    "industry": p.get("industry"),
                    "logo_url": f"https://icon.horse/icon/{domain}" if domain else None,
                }
            return {**comp, "ticker": ticker_sym}
    return comp


def get_stock_history(ticker: str, period: str) -> list[dict]:
    period_timeseries = {"1d": 2, "1mo": 30, "6mo": 180, "1y": 365, "5y": 1825}
    period_sample    = {"1d": 1, "1mo": 1, "6mo": 3, "1y": 5, "5y": 20}

    ts = period_timeseries.get(period, 365)
    sample = period_sample.get(period, 5)

    if period == "1d":
        data = _fmp(f"/v3/historical-chart/5min/{ticker}") or []
        points = []
        for pt in list(reversed(data))[-80:]:
            close = _safe_float(pt.get("close"))
            if close is None:
                continue
            points.append({
                "date": str(pt.get("date", "")),
                "close": close,
                "open": _safe_float(pt.get("open")),
                "high": _safe_float(pt.get("high")),
                "low": _safe_float(pt.get("low")),
                "volume": int(pt["volume"]) if pt.get("volume") else None,
                "change": 0.0, "change_pct": 0.0,
            })
        return points

    hist = _fmp(f"/v3/historical-price-full/{ticker}", timeseries=ts)
    if not isinstance(hist, dict) or not hist.get("historical"):
        return []

    daily = list(reversed(hist["historical"]))
    sampled = daily[::sample]
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
            "close": close,
            "open": _safe_float(pt.get("open")),
            "high": _safe_float(pt.get("high")),
            "low": _safe_float(pt.get("low")),
            "volume": int(pt["volume"]) if pt.get("volume") else None,
            "change": change,
            "change_pct": change_pct,
        })
        prev_close = close
    return points
