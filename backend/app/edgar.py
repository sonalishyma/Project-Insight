"""
SEC EDGAR integration — fetches recent material events (8-K) and
the business description from the latest 10-K for public companies.
No API key required; SEC requires a descriptive User-Agent.
"""

import re
import httpx

_HEADERS = {
    "User-Agent": "Insight Market Research ashikder0001@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}
_client = httpx.Client(timeout=12.0, headers=_HEADERS)

# Loaded once on first call; maps normalised company name → (ticker, cik)
_NAME_MAP: dict[str, tuple[str, str]] | None = None


def _norm(name: str) -> str:
    """Lowercase, strip common legal suffixes, collapse whitespace."""
    name = name.lower()
    name = re.sub(r"\b(inc|corp|ltd|llc|co|plc|group|holdings?|technologies?|systems?|the)\b\.?", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _load_name_map() -> dict[str, tuple[str, str]]:
    global _NAME_MAP
    if _NAME_MAP is not None:
        return _NAME_MAP
    result: dict[str, tuple[str, str]] = {}
    try:
        r = _client.get("https://www.sec.gov/files/company_tickers.json", timeout=15)
        for item in r.json().values():
            ticker = item.get("ticker", "")
            title = item.get("title", "")
            cik = str(item.get("cik_str", "")).zfill(10)
            if ticker and title:
                result[_norm(title)] = (ticker, cik)
    except Exception:
        pass
    _NAME_MAP = result
    return result


def find_ticker(company: str) -> tuple[str, str] | tuple[None, None]:
    """
    Return (ticker, cik) for a company name using SEC's company list.
    Falls back through exact → prefix → all-words matching.
    Returns (None, None) if not found.
    """
    name_map = _load_name_map()
    if not name_map:
        return None, None

    q = _norm(company)

    # 1. Exact match
    if q in name_map:
        return name_map[q]

    # 2. Map key starts with the query  (e.g. "nike" matches "nike inc")
    for key, val in name_map.items():
        if key.startswith(q):
            return val

    # 3. All words in query appear in the key
    words = q.split()
    if words:
        for key, val in name_map.items():
            if all(w in key for w in words):
                return val

    return None, None

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

def _get_cik(ticker: str) -> str | None:
    name_map = _load_name_map()
    ticker_upper = ticker.upper()
    for _ticker, cik in name_map.values():
        if _ticker == ticker_upper:
            return cik
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
