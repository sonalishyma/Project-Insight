"""
SEC EDGAR integration — fetches recent material events (8-K) and
the business description from the latest 10-K for public companies.
No API key required; SEC requires a descriptive User-Agent.
"""

import difflib
import re
import httpx

_HEADERS = {
    "User-Agent": "Insight Market Research ashikder0001@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}
_client = httpx.Client(timeout=12.0, headers=_HEADERS)

# Loaded once on first call; maps normalised company name → (ticker, cik)
_NAME_MAP: dict[str, tuple[str, str]] | None = None

# Hard overrides: checked before EDGAR lookup to handle rebrands, compound words,
# collision fixes, and companies absent from SEC's company_tickers.json.
# Keys are the raw-cleaned company name (punctuation→space, lowercased, squashed).
_TICKER_OVERRIDES: dict[str, str] = {
    # ── EDGAR collision fixes (wrong ticker wins the normalized key) ──
    "vertex pharmaceuticals": "VRTX",       # norm → "vertex" → VERX (tax software) wins
    "vertex pharmaceuticals inc": "VRTX",
    "boston properties": "BXP",             # norm → "boston" → BSX/SAM win
    "citizens financial": "CFG",            # norm → "citizens" → CZFS wins
    "citizens financial group": "CFG",
    "citizens financial group inc": "CFG",
    "lincoln national": "LNC",              # norm → "lincoln" → LECO wins
    "lincoln national corp": "LNC",
    "lincoln national corporation": "LNC",
    "hartford financial services": "HIG",   # norm → "hartford" → HFUS (shorter prefix)
    "hartford financial services group": "HIG",
    "franklin templeton": "BEN",            # norm exact match → FGDL ETF wins
    "franklin resources": "BEN",
    "marsh mclennan": "MMC",                # norm "marsh mclennan" → MRSH wins
    "marsh   mclennan": "MMC",              # & stripped variant
    "marsh mclennan companies": "MMC",
    "parker hannifin": "PH",                # EDGAR key is "parkerhannifin" (compound)
    "parker hannifin corp": "PH",
    "a o smith": "AOS",                     # EDGAR key is "smith a o" (inverted)
    "ao smith": "AOS",
    "ao smith corp": "AOS",
    "j b hunt transport services": "JBHT",  # EDGAR key is "hunt j b transport" (inverted)
    "jb hunt transport services": "JBHT",
    "j b hunt transport": "JBHT",
    "jb hunt transport": "JBHT",
    "d r horton": "DHI",                    # EDGAR key is "horton d r de" (inverted)
    "dr horton": "DHI",
    "d r horton inc": "DHI",
    "o reilly automotive": "ORLY",          # apostrophe stripped → norm mismatch
    "oreilly automotive": "ORLY",
    "vf corporation": "VFC",                # EDGAR key is "v f" (spaced initials)
    "vf corp": "VFC",
    "campbell soup": "CPB",                 # EDGAR key is "campbells" (different form)
    "campbell soup company": "CPB",
    "jm smucker": "SJM",                    # EDGAR key is "j m smucker" (spaced)
    "j m smucker": "SJM",
    "hess": "HES",                          # prefix match → HESM (midstream) wins
    "hess corporation": "HES",
    "sundance energy": "SNDE",              # prefix match → SUND wins
    "westrock": "WRK",                      # prefix match → WEST (coffee) wins
    "west rock": "WRK",
    "saic": "SAIC",                         # "mosaic" contains "saic" as substring
    # ── Ticker format mismatches (FMP expects different format than EDGAR) ──
    "berkshire hathaway": "BRK.B",          # EDGAR stores BRK-B; FMP uses BRK.B
    "berkshire hathaway inc": "BRK.B",
    # ── Rebrands / renamed companies ──
    "anthem": "ELV",                        # Anthem Inc → Elevance Health
    "anthem inc": "ELV",
    "raytheon technologies": "RTX",         # Raytheon Technologies → RTX Corp
    "raytheon": "RTX",
    "amerisourcebergen": "ABC",             # renamed to Cencora (COR)
    "amerisource bergen": "ABC",
    "amerisourcebergen corp": "ABC",
    "discovery": "WBD",                     # Discovery Inc → Warner Bros. Discovery
    "discovery inc": "WBD",
    "twitter": "TWTR",
    "twitter inc": "TWTR",
    "kellogg": "K",                         # Kellogg → Kellanova (still K ticker)
    "kellanova": "K",
    "kellogg company": "K",
    "fleetcor": "FLT",                      # FleetCor → Corpay
    "fleetcor technologies": "FLT",
    "xpo logistics": "XPO",                 # "logistics" not in norm strip list
    # ── Compound words (no space in user query, space in EDGAR) ──
    "exxonmobil": "XOM",                    # EDGAR: "exxon mobil" (two words)
    # ── Companies absent from EDGAR company_tickers.json ──
    "ansys": "ANSS",
    "ansys inc": "ANSS",
    "interpublic": "IPG",
    "interpublic group": "IPG",
    "comerica": "CMA",
    "comerica inc": "CMA",
    "discover financial": "DFS",
    "discover financial services": "DFS",
    "first republic bank": "FRC",
    "first republic": "FRC",
    "svb financial": "SIVB",
    "svb financial group": "SIVB",
    "signature bank": "SBNY",
    "new york community bancorp": "NYCB",
    "new york community": "NYCB",
    "everest re": "RE",
    "everest re group": "RE",
    "hologic": "HOLX",
    "hologic inc": "HOLX",
    "catalent": "CTLT",
    "catalent inc": "CTLT",
    "activision blizzard": "ATVI",
    "activision": "ATVI",
    "kansas city southern": "KSU",
    "spirit aerosystems": "SPR",
    "spirit aerosystems holdings": "SPR",
    "iaa": "IAA",
    "kar auction services": "KAR",
    "nielsen holdings": "NLSN",
    "ihs markit": "INFO",
    "dun bradstreet": "DNB",               # "Dun & Bradstreet" → & stripped
    "dun   bradstreet": "DNB",
    "pioneer natural resources": "PXD",
    "coterra energy": "CTRA",
    "coterra": "CTRA",
    "marathon oil": "MRO",
    "marathon oil corp": "MRO",
    "cabot oil   gas": "COG",              # "Cabot Oil & Gas" → & stripped
    "cabot oil and gas": "COG",
    "cabot oil gas": "COG",
    "reliance steel": "RS",                # EDGAR key "reliance" (just Inc form)
    "reliance steel   aluminum": "RS",
    "united states steel": "X",
    "united states steel corp": "X",
    "sealed air": "SEE",
    "sealed air corp": "SEE",
    "summit materials": "SUM",
    "us concrete": "USCR",
    "h b fuller": "FUL",                   # "H.B. Fuller" → dots stripped
    "hb fuller": "FUL",
    "store capital": "STOR",
    "national retail properties": "NNN",
    "south jersey industries": "SJI",
    "sjw group": "SJW",
    "pactiv evergreen": "PTVE",
    "schlumberger": "SLB",                 # renamed to SLB NV in EDGAR
    "schlumberger nv": "SLB",
    "take two interactive": "TTWO",        # prefix fixed by hyphen→space but override too
    "take two interactive software": "TTWO",
    "air products and chemicals": "APD",   # "and" connector not stripped by default
    "air products   chemicals": "APD",     # after & stripped
    # ── Dual-class share preference (prefer widely-traded class) ──
    "fox corporation": "FOX",             # prefer Class B (FOX) over Class A (FOXA)
    "fox": "FOX",                          # EDGAR exact "fox" → FOXA; prefer FOX
    "news corp": "NWS",                   # prefer Class B (NWS) over Class A (NWSA)
    "news corporation": "NWS",
    "brown forman": "BF.B",               # prefer Class B (BF.B); EDGAR has BF-A
    "brown forman corp": "BF.B",
    # ── Ticker symbol changes ──
    "fiserv": "FI",                       # Fiserv changed ticker FISV→FI in April 2024
    "fiserv inc": "FI",
    # ── Companies absent from EDGAR or with name collision ──
    "paramount global": "PARA",           # EDGAR "paramount" → PSKY (Paramount Skydance)
    "paramount": "PARA",
    "gap": "GPS",                          # Gap Inc NYSE ticker is GPS; EDGAR stores GAP
    "gap inc": "GPS",
    "constellation brands": "STZ",        # EDGAR "constellation" → CEG (different company)
    "constellation brands inc": "STZ",
}


def _norm(name: str) -> str:
    """Lowercase, replace hyphens with spaces, strip common legal suffixes, collapse whitespace."""
    name = name.lower()
    name = name.replace("-", " ")   # treat hyphens as spaces (e.g. Coca-Cola → coca cola)
    name = re.sub(
        r"\b(inc|incorporated|corp|corporation|ltd|limited|llc|co|company|companies|"
        r"plc|group|holdings?|technologies?|technology|systems?|the|and|"
        r"international|global|enterprises?|industries|solutions?|services?|"
        r"properties|financial|capital|energy|resources?|pharmaceuticals?|"
        r"chemicals?|brands?|electric|power|partners?|ventures?|labs?|"
        r"networks?|communications?|media|entertainment|healthcare|health|"
        r"bancorp|bancorporation|banc|trust)\b\.?",
        "", name
    )
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _load_name_map() -> dict[str, tuple[str, str]]:
    global _NAME_MAP
    if _NAME_MAP:  # only use cache if non-empty; empty dict means a previous fetch failed
        return _NAME_MAP
    result: dict[str, tuple[str, str]] = {}
    try:
        r = _client.get("https://www.sec.gov/files/company_tickers.json", timeout=20)
        r.raise_for_status()
        for item in r.json().values():
            ticker = item.get("ticker", "")
            title = item.get("title", "")
            cik = str(item.get("cik_str", "")).zfill(10)
            if not ticker or not title:
                continue
            key = _norm(title)
            existing = result.get(key)
            if existing is None:
                result[key] = (ticker, cik)
            elif "-" in existing[0] and "-" not in ticker:
                # Prefer common stock (no hyphen, e.g. "T") over
                # preferred/derivative shares (e.g. "T-PC", "T-A")
                result[key] = (ticker, cik)
        print(f"[EDGAR] loaded {len(result)} companies", flush=True)
    except Exception as e:
        print(f"[EDGAR] failed to load name map: {e}", flush=True)
    if result:  # only cache on success
        _NAME_MAP = result
    return result


def find_ticker(company: str) -> tuple[str, str] | tuple[None, None]:
    """
    Return (ticker, cik) for a company name using SEC's company list.
    Falls back through exact → shortest-prefix → exact-word matching.
    Returns (None, None) if not found.
    """
    # Stage 0: curated overrides — checked before EDGAR to fix rebrands,
    # collisions, and companies absent from company_tickers.json.
    # Use a lightly-cleaned key: punctuation→space, lowercase, squash.
    raw = re.sub(r"[^\w\s]", " ", company.lower())
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw in _TICKER_OVERRIDES:
        return _TICKER_OVERRIDES[raw], ""

    name_map = _load_name_map()
    if not name_map:
        return None, None

    q = _norm(company)
    if not q:
        return None, None

    # Stage 1: exact match on normalized name
    if q in name_map:
        return name_map[q]

    # Also check the post-norm form against overrides (catches "exxonmobil" etc.)
    if q in _TICKER_OVERRIDES:
        return _TICKER_OVERRIDES[q], ""

    # Stage 2: key starts with query + space (prevents short prefix grabbing unrelated company)
    prefix = q + " "
    candidates = [(key, val) for key, val in name_map.items() if key.startswith(prefix)]
    if candidates:
        return min(candidates, key=lambda kv: len(kv[0]))[1]

    # Stage 3: all query words appear as exact words in the key (2+ word queries only)
    words = q.split()
    if len(words) >= 2:
        key_words_map = [(key, set(key.split()), val) for key, val in name_map.items()]
        word_set = set(words)
        candidates = [(key, val) for key, kw, val in key_words_map if word_set <= kw]
        if candidates:
            return min(candidates, key=lambda kv: len(kv[0]))[1]

    # Stage 4: fuzzy match — last resort to handle single-character typos
    # (e.g. "NetIflix" → "netflix", "Microsft" → "microsoft")
    close = difflib.get_close_matches(q, name_map.keys(), n=1, cutoff=0.85)
    if close:
        return name_map[close[0]]

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
