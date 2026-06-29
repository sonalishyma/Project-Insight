"""
Media & Public Opinion intelligence.

Live sources (free, no auth):
  - Hacker News: Algolia search API
  - Reddit: Reddit search JSON endpoint

Source registry: 50 curated publications, VC blogs, podcasts, and influencers
organized into 5 tiers. Used by the frontend to show coverage and provide
direct search links for finding what each source says about a company.
"""

import httpx
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse, quote_plus

_client = httpx.Client(
    timeout=10.0,
    headers={"User-Agent": "Mozilla/5.0 (compatible; Insight/1.0)"},
    follow_redirects=True,
)

# ── Source Registry ───────────────────────────────────────────────────────────
# 50 curated sources organized into 5 tiers.
# "domain" used to match Tavily results; "search_url" is the direct search link.

SOURCE_REGISTRY = {
    # ── Tier 1: Major Business News ──────────────────────────────────────────
    "tier1": {
        "label": "Major Business News",
        "emoji": "📰",
        "sources": [
            {"name": "Bloomberg",        "domain": "bloomberg.com",      "url": "https://www.bloomberg.com/search?query={q}"},
            {"name": "Reuters",          "domain": "reuters.com",         "url": "https://www.reuters.com/search/news?blob={q}"},
            {"name": "CNBC",             "domain": "cnbc.com",            "url": "https://www.cnbc.com/search/?query={q}"},
            {"name": "Wall Street Journal","domain": "wsj.com",           "url": "https://www.wsj.com/search?query={q}"},
            {"name": "Financial Times",  "domain": "ft.com",              "url": "https://www.ft.com/search?q={q}"},
            {"name": "Forbes",           "domain": "forbes.com",          "url": "https://www.forbes.com/search/?q={q}"},
            {"name": "Fortune",          "domain": "fortune.com",         "url": "https://fortune.com/search/?s={q}"},
            {"name": "Business Insider", "domain": "businessinsider.com", "url": "https://www.businessinsider.com/s?q={q}"},
            {"name": "Axios",            "domain": "axios.com",           "url": "https://www.axios.com/search?q={q}"},
            {"name": "Yahoo Finance",    "domain": "finance.yahoo.com",   "url": "https://finance.yahoo.com/search/?p={q}"},
        ],
    },
    # ── Tier 2: Tech Journalism ───────────────────────────────────────────────
    "tier2": {
        "label": "Tech Journalism",
        "emoji": "💻",
        "sources": [
            {"name": "TechCrunch",        "domain": "techcrunch.com",       "url": "https://techcrunch.com/?s={q}"},
            {"name": "The Verge",         "domain": "theverge.com",         "url": "https://www.theverge.com/search?q={q}"},
            {"name": "Wired",             "domain": "wired.com",            "url": "https://www.wired.com/search/?q={q}"},
            {"name": "Ars Technica",      "domain": "arstechnica.com",      "url": "https://arstechnica.com/?s={q}"},
            {"name": "VentureBeat",       "domain": "venturebeat.com",      "url": "https://venturebeat.com/?s={q}"},
            {"name": "The Information",   "domain": "theinformation.com",   "url": "https://www.theinformation.com/search?q={q}"},
            {"name": "MIT Tech Review",   "domain": "technologyreview.com", "url": "https://www.technologyreview.com/search/?q={q}"},
            {"name": "IEEE Spectrum",     "domain": "spectrum.ieee.org",    "url": "https://spectrum.ieee.org/search#q={q}"},
            {"name": "404 Media",         "domain": "404media.co",          "url": "https://www.404media.co/search/?q={q}"},
            {"name": "Hacker News",       "domain": "news.ycombinator.com", "url": "https://hn.algolia.com/?query={q}&type=story"},
        ],
    },
    # ── Tier 3: Startup & VC Blogs ───────────────────────────────────────────
    "tier3": {
        "label": "Venture Capital & Startup",
        "emoji": "🚀",
        "sources": [
            {"name": "a16z",                    "domain": "a16z.com",             "url": "https://a16z.com/?s={q}"},
            {"name": "Y Combinator",            "domain": "ycombinator.com",      "url": "https://www.ycombinator.com/search?q={q}"},
            {"name": "Sequoia Capital",         "domain": "sequoiacap.com",       "url": "https://www.google.com/search?q=site:sequoiacap.com+{q}"},
            {"name": "First Round Review",      "domain": "firstround.com",       "url": "https://review.firstround.com/?s={q}"},
            {"name": "Greylock",                "domain": "greylock.com",         "url": "https://greylock.com/?s={q}"},
            {"name": "Bessemer Venture",        "domain": "bvp.com",              "url": "https://www.bvp.com/search?q={q}"},
            {"name": "Lightspeed",              "domain": "lsvp.com",             "url": "https://www.google.com/search?q=site:lsvp.com+{q}"},
            {"name": "General Catalyst",        "domain": "generalcatalyst.com",  "url": "https://www.google.com/search?q=site:generalcatalyst.com+{q}"},
            {"name": "Benchmark",               "domain": "benchmark.com",        "url": "https://www.google.com/search?q=site:benchmark.com+{q}"},
            {"name": "NFX",                     "domain": "nfx.com",              "url": "https://www.nfx.com/search?q={q}"},
        ],
    },
    # ── Tier 4: Podcasts & Long-Form ─────────────────────────────────────────
    "tier4": {
        "label": "Podcasts & Interviews",
        "emoji": "🎙️",
        "sources": [
            {"name": "All-In Podcast",      "domain": "allin.com",           "url": "https://www.google.com/search?q=All-In+Podcast+{q}"},
            {"name": "Acquired",            "domain": "acquired.fm",         "url": "https://www.acquired.fm/search?q={q}"},
            {"name": "Lenny's Podcast",     "domain": "lennysnewsletter.com","url": "https://www.lennysnewsletter.com/search?q={q}"},
            {"name": "TBPN",                "domain": "tbpn.com",            "url": "https://www.google.com/search?q=TBPN+{q}"},
            {"name": "Invest Like the Best","domain": "joincolossus.com",    "url": "https://www.joincolossus.com/search?q={q}"},
            {"name": "Lex Fridman Podcast", "domain": "lexfridman.com",      "url": "https://lexfridman.com/search?q={q}"},
            {"name": "BG2 Pod",             "domain": "bg2pod.com",          "url": "https://www.google.com/search?q=BG2+Pod+{q}"},
            {"name": "20VC",                "domain": "thetwentyminutevc.com","url": "https://www.google.com/search?q=20VC+{q}"},
            {"name": "My First Million",    "domain": "mfmpod.com",          "url": "https://www.google.com/search?q=%22My+First+Million%22+{q}"},
            {"name": "Decoder (The Verge)", "domain": "theverge.com",        "url": "https://www.google.com/search?q=Decoder+podcast+{q}"},
        ],
    },
    # ── Tier 5: Influential Individuals ──────────────────────────────────────
    "tier5": {
        "label": "Analysts & Thought Leaders",
        "emoji": "👤",
        "sources": [
            {"name": "Ben Thompson",        "domain": "stratechery.com",     "url": "https://stratechery.com/search/?q={q}", "handle": "@benthompson"},
            {"name": "Bill Gurley",         "domain": "abovethecrowd.com",   "url": "https://www.google.com/search?q=site:abovethecrowd.com+{q}", "handle": "@bgurley"},
            {"name": "Paul Graham",         "domain": "paulgraham.com",      "url": "https://www.google.com/search?q=%22Paul+Graham%22+{q}", "handle": "@paulg"},
            {"name": "Marc Andreessen",     "domain": "a16z.com",            "url": "https://www.google.com/search?q=%22Marc+Andreessen%22+{q}", "handle": "@pmarca"},
            {"name": "Garry Tan",           "domain": "ycombinator.com",     "url": "https://www.google.com/search?q=%22Garry+Tan%22+{q}", "handle": "@garrytan"},
            {"name": "Chamath Palihapitiya","domain": "allin.com",           "url": "https://www.google.com/search?q=%22Chamath%22+{q}", "handle": "@chamath"},
            {"name": "Jason Calacanis",     "domain": "launch.co",           "url": "https://www.google.com/search?q=%22Jason+Calacanis%22+{q}", "handle": "@jason"},
            {"name": "Tomasz Tunguz",       "domain": "tomtunguz.com",       "url": "https://tomtunguz.com/search/?q={q}", "handle": "@ttunguz"},
            {"name": "Packy McCormick",     "domain": "notboring.co",        "url": "https://www.notboring.co/search?q={q}", "handle": "@packym"},
            {"name": "Lex Fridman",         "domain": "lexfridman.com",      "url": "https://lexfridman.com/search?q={q}", "handle": "@lexfridman"},
        ],
    },
}

# Community platforms
COMMUNITY_PLATFORMS = [
    {"name": "Reddit",         "url": "https://www.reddit.com/search/?q={q}&sort=top",    "icon": "reddit"},
    {"name": "Hacker News",    "url": "https://hn.algolia.com/?query={q}&type=story",      "icon": "hn"},
    {"name": "X (Twitter)",    "url": "https://twitter.com/search?q={q}&f=live",           "icon": "x"},
    {"name": "LinkedIn",       "url": "https://www.linkedin.com/search/results/all/?keywords={q}", "icon": "linkedin"},
    {"name": "GitHub",         "url": "https://github.com/search?q={q}&type=repositories", "icon": "github"},
    {"name": "Product Hunt",   "url": "https://www.producthunt.com/search?q={q}",          "icon": "ph"},
    {"name": "Stack Overflow", "url": "https://stackoverflow.com/search?q={q}",            "icon": "so"},
]


# ── Domain normalizer ─────────────────────────────────────────────────────────

def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ── Build a flat domain → source lookup ──────────────────────────────────────

_DOMAIN_TO_SOURCE: dict[str, dict] = {}
for _tier_key, _tier_data in SOURCE_REGISTRY.items():
    for _src in _tier_data["sources"]:
        d = _src.get("domain", "")
        if d:
            _DOMAIN_TO_SOURCE[d] = {**_src, "tier": _tier_key, "tier_label": _tier_data["label"]}


# ── Live data fetchers ────────────────────────────────────────────────────────

def fetch_hn_mentions(company: str) -> list[dict]:
    """Hacker News posts mentioning the company, sorted by score."""
    try:
        r = _client.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query": company,
                "tags": "story",
                "hitsPerPage": 10,
                "numericFilters": "created_at_i>1640000000",  # after Jan 2022
            },
        )
        hits = r.json().get("hits", [])
        results = []
        for h in hits:
            title = (h.get("title") or "").strip()
            if not title:
                continue
            oid = h.get("objectID", "")
            results.append({
                "title": title,
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                "hn_url": f"https://news.ycombinator.com/item?id={oid}",
                "points": h.get("points") or 0,
                "comments": h.get("num_comments") or 0,
                "author": h.get("author") or "",
                "date": datetime.fromtimestamp(h["created_at_i"]).strftime("%Y-%m-%d") if h.get("created_at_i") else None,
            })
        results.sort(key=lambda x: x["points"], reverse=True)
        return results[:8]
    except Exception as e:
        print(f"[hn] search failed for '{company}': {e}", flush=True)
        return []


def fetch_reddit_mentions(company: str) -> list[dict]:
    """Reddit posts about the company from business/tech subreddits."""
    _SKIP_SUBREDDITS = {"memes", "funny", "pics", "gifs", "videos", "jokes", "gaming"}
    try:
        r = _client.get(
            "https://www.reddit.com/search.json",
            params={"q": company, "sort": "top", "t": "year", "limit": 15, "type": "link"},
            headers={"User-Agent": "Insight/1.0 (market research)"},
        )
        posts = r.json().get("data", {}).get("children", [])
        results = []
        for p in posts:
            d = p.get("data", {})
            title = (d.get("title") or "").strip()
            subreddit = d.get("subreddit") or ""
            if not title or subreddit.lower() in _SKIP_SUBREDDITS:
                continue
            ts = d.get("created_utc")
            results.append({
                "title": title,
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "subreddit": subreddit,
                "score": d.get("score") or 0,
                "upvote_ratio": d.get("upvote_ratio"),
                "comments": d.get("num_comments") or 0,
                "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else None,
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:8]
    except Exception as e:
        print(f"[reddit] search failed for '{company}': {e}", flush=True)
        return []


def categorize_sources(articles: list[dict]) -> dict[str, list[dict]]:
    """
    Match article URLs to the source registry.
    Returns a dict mapping tier key → list of (source, matched_articles).
    """
    by_domain: dict[str, list[dict]] = {}
    for a in articles:
        d = _domain_of(a.get("url", ""))
        by_domain.setdefault(d, []).append(a)

    hits: dict[str, dict] = {}  # domain → {source meta + matched articles}
    for domain, arts in by_domain.items():
        src = _DOMAIN_TO_SOURCE.get(domain)
        if src:
            hits[domain] = {**src, "articles": arts, "count": len(arts)}

    return hits


def build_search_urls(company: str) -> dict:
    """Build formatted search URLs for all sources with the company name injected."""
    q = quote_plus(company)
    registry_with_urls: dict[str, dict] = {}
    for tier_key, tier_data in SOURCE_REGISTRY.items():
        registry_with_urls[tier_key] = {
            **tier_data,
            "sources": [
                {**src, "search_url": src["url"].replace("{q}", q)}
                for src in tier_data["sources"]
            ],
        }
    community = [
        {**p, "search_url": p["url"].replace("{q}", q)}
        for p in COMMUNITY_PLATFORMS
    ]
    return {"tiers": registry_with_urls, "community": community}


# ── Main aggregator ───────────────────────────────────────────────────────────

def fetch_media_overview(company: str, existing_articles: list[dict] | None = None) -> dict:
    """
    Fetch community discussion and categorize media coverage.
    HN and Reddit run in parallel (both free, no auth).
    """
    with ThreadPoolExecutor(max_workers=2) as ex:
        hn_fut = ex.submit(fetch_hn_mentions, company)
        rd_fut = ex.submit(fetch_reddit_mentions, company)

    hn_posts = hn_fut.result()
    reddit_posts = rd_fut.result()

    source_hits = categorize_sources(existing_articles or [])
    registry = build_search_urls(company)

    return {
        "hn_posts": hn_posts,
        "reddit_posts": reddit_posts,
        "source_hits": source_hits,  # which registry sources have matched articles
        "registry": registry,        # full 50-source registry with formatted search URLs
    }
