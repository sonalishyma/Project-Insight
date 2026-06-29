"""
Social sentiment — StockTwits stream (no API key required).
Used to show retail trader bullish/bearish sentiment and recent top posts.
"""

import httpx

_client = httpx.Client(
    timeout=8.0,
    headers={"User-Agent": "Mozilla/5.0 (compatible; Insight/1.0)"},
    follow_redirects=True,
)


def fetch_stocktwits(ticker: str) -> dict:
    """
    Fetch recent posts and sentiment from StockTwits for a stock ticker.
    Returns bullish/bearish counts and top posts sorted by follower count.
    """
    try:
        r = _client.get(
            f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json",
            params={"limit": 30},
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        if data.get("errors"):
            return {}

        messages = data.get("messages", [])
        bullish = sum(
            1 for m in messages
            if (m.get("entities") or {}).get("sentiment", {}).get("basic") == "Bullish"
        )
        bearish = sum(
            1 for m in messages
            if (m.get("entities") or {}).get("sentiment", {}).get("basic") == "Bearish"
        )
        total_sentiment = bullish + bearish

        # Sort by follower count to surface the most-followed voices first
        sorted_msgs = sorted(
            messages,
            key=lambda m: m.get("user", {}).get("followers", 0),
            reverse=True,
        )

        posts = []
        for m in sorted_msgs[:10]:
            body = (m.get("body") or "").strip()
            if not body or len(body) < 15:
                continue
            sentiment = (
                (m.get("entities") or {}).get("sentiment", {}).get("basic")
                if m.get("entities") else None
            )
            user = m.get("user") or {}
            posts.append({
                "text": body[:300],
                "user": user.get("username", ""),
                "followers": user.get("followers", 0),
                "verified": user.get("official", False),
                "sentiment": sentiment,
                "date": (m.get("created_at") or "")[:10] or None,
            })
            if len(posts) >= 6:
                break

        return {
            "bullish_count": bullish,
            "bearish_count": bearish,
            "total": len(messages),
            "bullish_pct": round(bullish / total_sentiment * 100) if total_sentiment > 0 else None,
            "posts": posts,
        }
    except Exception as e:
        print(f"[stocktwits] failed for {ticker}: {e}", flush=True)
        return {}
