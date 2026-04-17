import asyncio
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx

from app.models.responses import Source

# -----------------------------------------------------------------------------
# Domain Tier Registry
# Tier 1 = Global Wire Services (highest trust)
# Tier 2 = Dedicated Fact-Checkers
# Tier 3 = Mainstream News (varying editorial bias)
# Tier 4 = Ideological / Opinion / Hyperpartisan
# Tier 5 = Known disinformation / pseudoscience (penalty tier)
# -----------------------------------------------------------------------------
DOMAIN_TIERS: dict[str, int] = {
    # --- Tier 1: Wire Services ---
    "reuters.com": 1,
    "apnews.com": 1,
    "pti.in": 1,
    "ani.in": 1,
    "afp.com": 1,
    "bloomberg.com": 1,
    # --- Tier 2: Fact-Checkers ---
    "altnews.in": 2,
    "boomlive.in": 2,
    "factchecker.in": 2,
    "vishvasnews.com": 2,
    "indiacheck.org": 2,
    "snopes.com": 2,
    "politifact.com": 2,
    "factcheck.org": 2,
    "fullfact.org": 2,
    "leadstories.com": 2,
    # --- Tier 3: Mainstream News ---
    "thehindu.com": 3,
    "indianexpress.com": 3,
    "ndtv.com": 3,
    "timesofindia.indiatimes.com": 3,
    "hindustantimes.com": 3,
    "bbc.com": 3,
    "bbc.co.uk": 3,
    "theguardian.com": 3,
    "nytimes.com": 3,
    "washingtonpost.com": 3,
    "theprint.in": 3,
    "scroll.in": 3,
    "livemint.com": 3,
    "businessstandard.com": 3,
    "economictimes.indiatimes.com": 3,
    "wionews.com": 3,
    # --- Tier 4: Ideological / Opinion ---
    "opindia.com": 4,
    "thewire.in": 4,
    "swarajyamag.com": 4,
    "newslaundry.com": 4,
    "theintercept.com": 4,
    "breitbart.com": 4,
    "thefederalist.com": 4,
    # --- Tier 5: Known Disinfo / Pseudoscience (penalty) ---
    "naturalnews.com": 5,
    "infowars.com": 5,
    "postcard.news": 5,
    "sudarshannews.com": 5,
    "kreately.in": 5,
}

# HTML tags to strip when extracting article text
_TAG_RE = re.compile(r"<[^>]+>")
# Collapse whitespace
_WS_RE = re.compile(r"\s+")

# Headers that mimic a real browser to avoid 403s on news sites
_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Max characters to keep from a scraped article body
_MAX_ARTICLE_CHARS = 1500


def _get_tier(url: str) -> int:
    """Return the tier for a URL, defaulting to 3 (mainstream)."""
    domain = url.split("//")[-1].split("/")[0].replace("www.", "").lower()
    # Try exact match, then parent domain
    if domain in DOMAIN_TIERS:
        return DOMAIN_TIERS[domain]
    parts = domain.split(".")
    if len(parts) > 2:
        parent = ".".join(parts[-2:])
        if parent in DOMAIN_TIERS:
            return DOMAIN_TIERS[parent]
    return 3


def _extract_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace to get readable text."""
    # Remove scripts and styles entirely
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = _TAG_RE.sub(" ", html)
    text = _WS_RE.sub(" ", text).strip()
    return text[:_MAX_ARTICLE_CHARS]


class LiveSearchModule:
    def __init__(self):
        self.search_client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
        self.scrape_client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0),
            follow_redirects=True,
            headers=_SCRAPE_HEADERS,
        )

    async def _scrape_article(self, url: str) -> Optional[str]:
        """Fetch and extract the main text of an article URL. Returns None on failure."""
        # Skip Google's redirect links — they can't be scraped directly
        if "news.google.com" in url:
            return None
        try:
            response = await self.scrape_client.get(url)
            if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
                return _extract_text(response.text)
        except Exception:
            pass
        return None

    async def _fetch_google_news(self, query: str, max_results: int) -> List[dict]:
        """Pull headlines from Google News RSS."""
        items = []
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
            response = await self.search_client.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            for item in root.findall("./channel/item")[:max_results]:
                title_node = item.find("title")
                link_node = item.find("link")
                date_node = item.find("pubDate")
                if title_node is None or link_node is None:
                    continue
                items.append({
                    "title": title_node.text or "",
                    "url": link_node.text or "",
                    "date": date_node.text if date_node is not None else "Unknown Date",
                })
        except Exception as e:
            print(f"Google News RSS error: {e}")
        return items

    async def _fetch_fact_checks(self, query: str, api_key: str) -> List[Source]:
        """
        Query the Google Fact Check Tools API.
        Returns pre-verified claims from organizations like Snopes, AltNews, etc.
        """
        if not api_key:
            return []
        sources = []
        try:
            params = {
                "query": query,
                "key": api_key,
                "languageCode": "en",
                "pageSize": 5,
            }
            response = await self.search_client.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params=params,
            )
            if response.status_code != 200:
                print(f"Fact Check API error: {response.status_code} {response.text[:200]}")
                return []
            data = response.json()
            for claim in data.get("claims", []):
                text = claim.get("text", "")
                for review in claim.get("claimReview", []):
                    publisher = review.get("publisher", {}).get("name", "Unknown Fact-Checker")
                    rating = review.get("textualRating", "Unknown")
                    review_url = review.get("url", "")
                    title = f"[Tier 2 - Fact Check] {publisher}: \"{text}\" → {rating}"
                    content = (
                        f"URL: {review_url}\n"
                        f"Claim: {text}\n"
                        f"Rating by {publisher}: {rating}"
                    )
                    sources.append(Source(title=title, content=content))
        except Exception as e:
            print(f"Fact Check API exception: {e}")
        return sources

    async def search(self, query: str, max_results: int = 5, fact_check_api_key: str = "") -> List[Source]:
        """
        Full evidence pipeline:
        1. Fetch headlines from Google News RSS
        2. Scrape actual article content from top URLs (concurrently)
        3. Append pre-verified fact-checks from Google Fact Check Tools API
        """
        # Step 1: Get headlines
        raw_items = await self._fetch_google_news(query, max_results)

        # Step 2: Scrape article bodies concurrently for the top items
        scrape_tasks = [self._scrape_article(item["url"]) for item in raw_items]
        scraped_bodies = await asyncio.gather(*scrape_tasks)

        sources: List[Source] = []
        for item, body in zip(raw_items, scraped_bodies):
            tier = _get_tier(item["url"])
            tier_label = f"Tier {tier}"
            headline = item["title"]
            date = item["date"]

            if body:
                # We have real article content
                content = (
                    f"URL: {item['url']}\n"
                    f"Published: {date}\n"
                    f"Article excerpt:\n{body}"
                )
            else:
                # Fall back to headline-only (better than nothing)
                content = (
                    f"URL: {item['url']}\n"
                    f"Published: {date}\n"
                    f"Snippet: {headline}"
                )

            title = f"[{tier_label}] {headline} ({date})"
            sources.append(Source(title=title, content=content))

        # Step 3: Prepend fact-checks (highest signal — put them first)
        fact_check_sources = await self._fetch_fact_checks(query, fact_check_api_key)

        return fact_check_sources + sources

    async def close(self) -> None:
        await self.search_client.aclose()
        await self.scrape_client.aclose()
