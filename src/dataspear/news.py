"""Market news feed via the Google News RSS endpoint.

No API key and no ``gnews`` dependency - just ``httpx`` plus the stdlib XML
parser. Headlines are scored for sentiment (BULLISH/BEARISH/NEUTRAL) and
impact (HIGH/MEDIUM/LOW) with keyword heuristics, then deduplicated.

    articles = await fetch_all_news(days=2)
    print(await news_brief(days=1))
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List
from urllib.parse import quote_plus

import httpx

log = logging.getLogger(__name__)

GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_DEFAULT_TIMEOUT = 15.0

# Query templates per category.
QUERIES = {
    "market": (
        "NIFTY OR NSE OR BSE OR Sensex OR Indian stock market OR "
        "FII OR DII OR India GDP OR RBI OR SEBI"
    ),
    "geopolitical": (
        "geopolitics OR sanctions OR oil price OR crude oil OR US Fed OR "
        "Federal Reserve OR China economy OR OPEC OR dollar index"
    ),
    "rbi_sebi": (
        "RBI policy OR repo rate OR monetary policy OR SEBI OR "
        "circuit breaker OR FPI limit OR derivatives regulation"
    ),
    "fii_flow": (
        "FII buying OR FII selling OR foreign portfolio OR FPI flows OR "
        "DII buying OR institutional investors India"
    ),
}

_BULLISH_WORDS = {
    "rally", "surge", "jump", "gain", "rise", "bullish", "positive",
    "recovery", "rebound", "upside", "growth", "rate cut", "stimulus",
    "buying", "inflow", "invest", "strong", "record high", "breakout",
}
_BEARISH_WORDS = {
    "fall", "crash", "drop", "decline", "sell", "bearish", "negative",
    "recession", "inflation", "outflow", "withdraw", "weak", "concern",
    "war", "sanction", "rate hike", "selloff", "correction", "breakdown",
}
_HIGH_IMPACT = {
    "rbi", "repo rate", "fed", "federal reserve", "gdp", "inflation",
    "war", "sanction", "circuit breaker", "sebi ban", "budget",
    "crude oil", "dollar index", "fii", "fpi",
}


@dataclass
class NewsArticle:
    title: str
    source: str
    published: str
    url: str
    category: str
    sentiment: str = "NEUTRAL"
    impact: str = "MEDIUM"

    def one_line(self) -> str:
        icon = {"BULLISH": "[+]", "BEARISH": "[-]", "NEUTRAL": "[ ]"}.get(
            self.sentiment, "[ ]"
        )
        imp = {"HIGH": "!", "MEDIUM": "-", "LOW": "."}.get(self.impact, ".")
        return f"{icon}{imp} [{self.source}] {self.title}"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "published": self.published,
            "url": self.url,
            "category": self.category,
            "sentiment": self.sentiment,
            "impact": self.impact,
        }


def score_article(title: str, category: str) -> tuple:
    """Return ``(sentiment, impact)`` for a headline (keyword heuristics)."""
    low = title.lower()
    bull = sum(1 for w in _BULLISH_WORDS if w in low)
    bear = sum(1 for w in _BEARISH_WORDS if w in low)

    if bull > bear:
        sentiment = "BULLISH"
    elif bear > bull:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    impact = "HIGH" if any(w in low for w in _HIGH_IMPACT) else "MEDIUM"
    if category == "geopolitical" and sentiment == "BEARISH":
        impact = "HIGH"
    return sentiment, impact


def _item_source(item: ET.Element) -> str:
    for child in item:
        if child.tag.endswith("source") and child.text:
            return child.text.strip()
    return "Unknown"


def _item_text(item: ET.Element, tag: str) -> str:
    for child in item:
        if child.tag == tag and child.text:
            return child.text.strip()
    return ""


def parse_rss(
    xml_text: str, category: str = "market", max_results: int = 8
) -> List[NewsArticle]:
    """Parse a Google News RSS document into scored, deduplicated articles."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("RSS parse failed: %s", exc)
        return []

    articles: List[NewsArticle] = []
    seen = set()
    for item in root.iter("item"):
        title = _item_text(item, "title")
        if not title or title in seen:
            continue
        seen.add(title)
        sentiment, impact = score_article(title, category)
        articles.append(
            NewsArticle(
                title=title,
                source=_item_source(item),
                published=_item_text(item, "pubDate"),
                url=_item_text(item, "link"),
                category=category,
                sentiment=sentiment,
                impact=impact,
            )
        )
        if len(articles) >= max_results:
            break
    return articles


def _is_recent(published: str, days: int) -> bool:
    if not published:
        return True
    try:
        dt = parsedate_to_datetime(published)
    except (TypeError, ValueError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=max(days, 1))


async def fetch_news(
    query: str,
    category: str = "market",
    days: int = 1,
    max_results: int = 8,
    timeout: float = _DEFAULT_TIMEOUT,
) -> List[NewsArticle]:
    """Fetch and score headlines for a raw query string."""
    url = GOOGLE_NEWS_URL.format(query=quote_plus(query))
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
    except httpx.HTTPError as exc:
        log.warning("News fetch failed [%s]: %s", category, exc)
        return []

    articles = parse_rss(text, category=category, max_results=max_results)
    return [a for a in articles if _is_recent(a.published, days)]


async def fetch_market_news(days: int = 1) -> List[NewsArticle]:
    return await fetch_news(QUERIES["market"], "market", days=days, max_results=8)


async def fetch_geopolitical_news(days: int = 2) -> List[NewsArticle]:
    return await fetch_news(
        QUERIES["geopolitical"], "geopolitical", days=days, max_results=8
    )


async def fetch_rbi_sebi_news(days: int = 3) -> List[NewsArticle]:
    return await fetch_news(
        QUERIES["rbi_sebi"], "rbi_sebi", days=days, max_results=6
    )


async def fetch_fii_news(days: int = 1) -> List[NewsArticle]:
    return await fetch_news(QUERIES["fii_flow"], "fii_flow", days=days, max_results=6)


async def fetch_all_news(days: int = 2) -> List[NewsArticle]:
    """All categories, deduplicated, HIGH impact first."""
    batches = [
        await fetch_market_news(days=days),
        await fetch_fii_news(days=days),
        await fetch_rbi_sebi_news(days=days),
        await fetch_geopolitical_news(days=days),
    ]

    seen = set()
    articles: List[NewsArticle] = []
    for batch in batches:
        for article in batch:
            if article.title not in seen:
                seen.add(article.title)
                articles.append(article)

    def sort_key(a: NewsArticle) -> tuple:
        imp = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(a.impact, 2)
        sen = {"BEARISH": 0, "BULLISH": 0, "NEUTRAL": 1}.get(a.sentiment, 1)
        return (imp, sen)

    return sorted(articles, key=sort_key)


def render_news_brief(articles: List[NewsArticle]) -> str:
    """Render a compact summary block from already-fetched articles."""
    if not articles:
        return "No market news available."

    high = [a for a in articles if a.impact == "HIGH"][:4]
    medium = [a for a in articles if a.impact == "MEDIUM"][:3]

    lines = ["=== MARKET NEWS ==="]
    lines.extend(a.one_line() for a in high + medium)

    bulls = sum(1 for a in articles if a.sentiment == "BULLISH")
    bears = sum(1 for a in articles if a.sentiment == "BEARISH")
    total = len(articles)
    if total:
        if bulls > bears * 1.5:
            overall = "NEWS SENTIMENT: BULLISH"
        elif bears > bulls * 1.5:
            overall = "NEWS SENTIMENT: BEARISH"
        else:
            overall = "NEWS SENTIMENT: MIXED"
        lines.append(f"{overall} ({bulls} bullish / {bears} bearish of {total})")

    lines.append("=== END NEWS ===")
    return "\n".join(lines)


async def news_brief(days: int = 1) -> str:
    """Compact news summary suitable for prompt injection."""
    return render_news_brief(await fetch_all_news(days=days))
