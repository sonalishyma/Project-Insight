import os
import re
from urllib.parse import urlparse

from tavily import TavilyClient

_client: TavilyClient | None = None

STARTUP_EXTRA_DOMAINS = [
    "crunchbase.com", "pitchbook.com", "tracxn.com", "sifted.eu",
    "strictlyvc.com", "dealroom.co", "angel.co", "carta.com",
    "f6s.com", "builtin.com", "cbinsights.com",
]

TRUSTED_DOMAINS = [
    "sec.gov",
    "bloomberg.com",
    "reuters.com",
    "wsj.com",
    "ft.com",
    "economist.com",
    "marketwatch.com",
    "cnbc.com",
    "forbes.com",
    "fortune.com",
    "businessinsider.com",
    "barrons.com",
    "morningstar.com",
    "seekingalpha.com",
    "finance.yahoo.com",
    "investopedia.com",
    "fool.com",
    "statista.com",
    "gartner.com",
    "forrester.com",
    "idc.com",
    "grandviewresearch.com",
    "marketsandmarkets.com",
    "researchandmarkets.com",
    "preceedenceresearch.com",
    "companiesmarketcap.com",
    "macrotrends.net",
    "nasdaq.com",
    "nyse.com",
    "tradingview.com",
    "techcrunch.com",
    "wired.com",
    "theinformation.com",
    "venturebeat.com",
    "arstechnica.com",
    "theverge.com",
    "zdnet.com",
    "hbr.org",
    "fastcompany.com",
    "inc.com",
    "entrepreneur.com",
    "nytimes.com",
    "theguardian.com",
    "apnews.com",
    "axios.com",
    "worldbank.org",
    "fred.stlouisfed.org",
    "oecd.org",
    "imf.org",
    "bea.gov",
    "bls.gov",
    "census.gov",
]


def _clean_snippet(text: str, max_len: int) -> str:
    """
    Tavily's scraped `content` carries raw page artifacts — markdown heading
    markers from <h2>/<h3> tags, bold/italic asterisks, and repeated "opens new
    tab" link-accessibility text — that read fine to an LLM but look broken
    rendered as-is in the UI. Strip those, then truncate on a word boundary
    instead of mid-word.
    """
    if not text:
        return text
    for zero_width in ('\u200b', '\u200c', '\u200d', '\ufeff'):
        text = text.replace(zero_width, '')
    text = re.sub(r'\bopens new tab\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\*{1,3}', '', text)              # bold/italic markers — strip before heading check below
    text = re.sub(r'#{1,6}\s+(?=[A-Z])', '', text)  # markdown headings, wherever they land
    text = re.sub(r'\s*,\s*,', ',', text)             # doubled commas left by removed link text
    text = re.sub(r'\.{2,}', '.', text)               # doubled periods left by removed markers
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([,.;:])', r'\1', text)
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_space = truncated.rfind(' ')
    if last_space > max_len * 0.6:
        truncated = truncated[:last_space]
    return truncated.rstrip('.,;:') + '…'


_BOILERPLATE_MARKERS = ('cookie', 'tracking technolog', 'subscribe to our newsletter', 'sign up for our newsletter')


def _is_boilerplate(text: str) -> bool:
    """
    Tavily occasionally scrapes a cookie-consent banner instead of the article body.
    Check only the leading chars — the same window a reader would actually see —
    since a legitimate article can mention "cookies" in passing much further down.
    """
    lowered = text[:250].lower()
    return any(m in lowered for m in _BOILERPLATE_MARKERS)


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _client


def fetch(company: str) -> list[dict]:
    """Run two searches (strategy + recent news) and combine, deduplicated by URL."""
    client = _get_client()
    seen: set[str] = set()
    results: list[dict] = []

    queries = [
        {
            "query": f"{company} market analysis business strategy competitive landscape",
            "search_depth": "basic",
            "max_results": 6,
            "topic": "general",
        },
        {
            "query": f"{company} competitors rival companies market share comparison",
            "search_depth": "basic",
            "max_results": 5,
            "topic": "general",
        },
        {
            "query": f"{company} earnings revenue financial results news",
            "search_depth": "basic",
            "max_results": 5,
            "topic": "news",
            "days": 30,
        },
    ]

    for params in queries:
        try:
            resp = client.search(**params, include_domains=TRUSTED_DOMAINS)
            for r in resp.get("results", []):
                url = r["url"]
                if url not in seen:
                    seen.add(url)
                    results.append({
                        "title": r["title"],
                        "url": url,
                        "snippet": r.get("content", ""),
                        "date": r.get("published_date"),
                    })
        except Exception:
            pass

    # Sort: dated articles newest-first, undated articles at end
    results.sort(key=lambda r: r.get("date") or "", reverse=True)
    return results


def fetch_private(company: str) -> list[dict]:
    """For private/startup companies: targets funding, investors, growth, and milestones."""
    client = _get_client()
    seen: set[str] = set()
    results: list[dict] = []
    all_domains = list(set(TRUSTED_DOMAINS + STARTUP_EXTRA_DOMAINS))

    queries = [
        {
            "query": f"{company} startup funding round investors raised series seed",
            "search_depth": "basic",
            "max_results": 7,
            "topic": "general",
        },
        {
            "query": f"{company} competitors alternatives rival companies similar market",
            "search_depth": "basic",
            "max_results": 6,
            "topic": "general",
        },
        {
            "query": f"{company} market analysis competitive landscape business strategy",
            "search_depth": "basic",
            "max_results": 5,
            "topic": "general",
        },
        {
            "query": f"{company} news employees growth customers partnerships enterprise",
            "search_depth": "basic",
            "max_results": 5,
            "topic": "news",
            "days": 90,
        },
        {
            "query": f"{company} company history founded milestones product launch valuation",
            "search_depth": "basic",
            "max_results": 4,
            "topic": "general",
        },
    ]

    for params in queries:
        try:
            resp = client.search(**params, include_domains=all_domains)
            for r in resp.get("results", []):
                url = r["url"]
                if url not in seen:
                    seen.add(url)
                    results.append({
                        "title": r["title"],
                        "url": url,
                        "snippet": r.get("content", ""),
                        "date": r.get("published_date"),
                    })
        except Exception:
            pass

    results.sort(key=lambda r: r.get("date") or "", reverse=True)
    return results


def fetch_news(company: str, days: int = 30) -> list[dict]:
    """Recent headlines for the Latest News section — news topic only."""
    try:
        resp = _get_client().search(
            query=f"{company} news",
            search_depth="basic",
            topic="news",
            days=days,
            max_results=5,
            include_domains=TRUSTED_DOMAINS,
        )
        return [
            {
                "title": r["title"],
                "url": r["url"],
                "date": r.get("published_date"),
                "snippet": _clean_snippet(r.get("content", ""), 200),
            }
            for r in resp.get("results", [])
            if not _is_boilerplate(r.get("content", ""))
        ]
    except Exception:
        return []


def fetch_social_links(company: str) -> dict:
    """
    Find official social profile URLs via a targeted search, matched deterministically
    by domain rather than asking the LLM to guess — a wrong URL here is a broken link,
    not just a weak paragraph, so we don't want hallucination risk in this field.
    """
    links: dict[str, str] = {}
    try:
        resp = _get_client().search(
            query=f"{company} official Twitter LinkedIn Instagram",
            search_depth="basic",
            max_results=8,
            topic="general",
        )
        for r in resp.get("results", []):
            url = r.get("url", "")
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "").lower()
            path = parsed.path.strip("/")
            if domain in ("twitter.com", "x.com") and "twitter_url" not in links:
                if path and "/" not in path:  # profile URL, not a status/tweet link
                    links["twitter_url"] = url
            elif domain == "linkedin.com" and "linkedin_url" not in links:
                if path.startswith("company/"):
                    links["linkedin_url"] = url
            elif domain == "instagram.com" and "instagram_url" not in links:
                if path and "/" not in path:
                    links["instagram_url"] = url
    except Exception:
        pass
    return links


def fetch_recent_signals(company: str, days: int = 7) -> list[dict]:
    """
    Recent social-adjacent posts/announcements, retrieved through search snippets rather
    than platform APIs (X's read API is paid-tier only; Instagram/LinkedIn have no public
    read access for arbitrary accounts). Falls back to general web results when nothing
    from the social platforms themselves is indexed for this window.
    """
    signals: list[dict] = []
    try:
        resp = _get_client().search(
            query=f'"{company}" announcement OR update OR launches',
            search_depth="basic",
            topic="news",
            days=days,
            max_results=6,
        )
        for r in resp.get("results", []):
            url = r.get("url", "")
            content = r.get("content", "")
            if not content or _is_boilerplate(content):
                continue
            domain = urlparse(url).netloc.replace("www.", "").lower()
            if domain in ("twitter.com", "x.com"):
                platform = "twitter"
            elif domain == "linkedin.com":
                platform = "linkedin"
            else:
                platform = "web"
            cleaned = _clean_snippet(content, 280)
            if not cleaned:
                continue
            signals.append({
                "platform": platform,
                "text": cleaned,
                "url": url,
                "date": r.get("published_date"),
            })
    except Exception:
        pass
    return signals


def format_context(articles: list[dict]) -> str:
    lines = ["Web search results (sorted newest first):\n"]
    for i, a in enumerate(articles, 1):
        date_tag = f" [{a['date']}]" if a.get("date") else ""
        lines.append(f"[{i}] {a['title']}{date_tag}\n    URL: {a['url']}\n    {a['snippet']}\n")
    return "\n".join(lines)
