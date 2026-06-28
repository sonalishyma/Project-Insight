"""
SEC EDGAR integration — fetches recent material events (8-K) and
the business description from the latest 10-K for public companies.
No API key required; SEC requires a descriptive User-Agent.
"""

import httpx

_HEADERS = {
    "User-Agent": "Insight Market Research ashikder0001@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}
_client = httpx.Client(timeout=12.0, headers=_HEADERS)

# 8-K item codes → plain-English labels
_8K_ITEMS: dict[str, str] = {
    "1.01": "entered a material agreement",
    "1.02": "terminated a material agreement",
    "1.03": "filed for bankruptcy/receivership",
    "2.01": "completed an acquisition or disposal",
    "2.02": "released results of operations",
    "2.04": "triggering events affecting debt",
    "2.05": "announced cost-cutting / restructuring",
    "2.06": "asset impairment recorded",
    "3.01": "received delisting notification",
    "4.01": "changed auditors",
    "5.01": "change of control",
    "5.02": "executive leadership change",
    "5.03": "amended charter or bylaws",
    "7.01": "Regulation FD disclosure",
    "8.01": "other material event",
}

_CIK_CACHE: dict[str, str] = {}


def _get_cik(ticker: str) -> str | None:
    ticker = ticker.upper()
    if ticker in _CIK_CACHE:
        return _CIK_CACHE[ticker]
    try:
        r = _client.get("https://www.sec.gov/files/company_tickers.json")
        for item in r.json().values():
            if item.get("ticker", "").upper() == ticker:
                cik = str(item["cik_str"]).zfill(10)
                _CIK_CACHE[ticker] = cik
                return cik
    except Exception:
        pass
    return None


def fetch_recent_events(ticker: str, cik: str | None = None, limit: int = 8) -> list[str]:
    """
    Return a list of plain-English strings describing the most recent
    8-K filings for the company, e.g.:
      ["2024-11-12: executive leadership change",
       "2024-10-31: released results of operations"]
    Returns [] if EDGAR is unreachable or the ticker is unknown.
    """
    try:
        if not cik:
            cik = _get_cik(ticker)
        if not cik:
            return []

        r = _client.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        filings = r.json().get("filings", {}).get("recent", {})

        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        items_list = filings.get("items", [])

        events: list[str] = []
        for form, date, items_str in zip(forms, dates, items_list):
            if form != "8-K":
                continue
            if not items_str:
                continue
            # items_str looks like "5.02,9.01" — map codes to labels
            codes = [c.strip() for c in str(items_str).split(",")]
            labels = [_8K_ITEMS[c] for c in codes if c in _8K_ITEMS]
            if labels:
                events.append(f"{date}: {'; '.join(labels)}")
            if len(events) >= limit:
                break

        return events
    except Exception:
        return []


def format_events_context(events: list[str], company: str) -> str:
    """Format the events list as a context block for the LLM."""
    if not events:
        return ""
    lines = "\n".join(f"  - {e}" for e in events)
    return f"\nRecent SEC filings (8-K) for {company}:\n{lines}"
