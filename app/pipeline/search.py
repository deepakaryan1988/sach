import asyncio
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict

import httpx

from app.models.responses import Source

# -----------------------------------------------------------------------------
# Domain Tier Registry
# Tier 1 = Global Wire Services (highest trust)
# Tier 2 = Dedicated Fact-Checkers (IFCN-certified where possible)
# Tier 3 = Mainstream News (varying editorial bias)
# Tier 4 = Ideological / Opinion / Hyperpartisan
# Tier 5 = Known disinformation / pseudoscience (penalty tier)
# -----------------------------------------------------------------------------
DOMAIN_TIERS: dict[str, int] = {
    # --- Tier 1: Wire Services ---
    "reuters.com": 1,
    "apnews.com": 1,
    "afp.com": 1,
    "bloomberg.com": 1,
    # --- Tier 1-GOV: Government-aligned wire (tagged separately) ---
    "pti.in": 1,
    "ani.in": 1,
    # --- Tier 2: IFCN-Certified Fact-Checkers ---
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
    "africacheck.org": 2,
    "chequeado.com": 2,
    "correctiv.org": 2,
    "pesacheck.org": 2,
    "dubawa.org": 2,
    "maldita.es": 2,
    "logically.ai": 2,
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
    "aljazeera.com": 3,
    "dw.com": 3,
    "france24.com": 3,
    "abc.net.au": 3,
    "cbc.ca": 3,
    "scmp.com": 3,
    # --- Tier 4: Ideological / Opinion ---
    "opindia.com": 4,
    "thewire.in": 4,
    "swarajyamag.com": 4,
    "newslaundry.com": 4,
    "theintercept.com": 4,
    "breitbart.com": 4,
    "thefederalist.com": 4,
    "foxnews.com": 4,
    "dailywire.com": 4,
    "thequint.com": 4,
    # --- Tier 5: Known Disinfo / Pseudoscience (penalty) ---
    "naturalnews.com": 5,
    "infowars.com": 5,
    "postcard.news": 5,
    "sudarshannews.com": 5,
    "kreately.in": 5,
    "greatgameindia.com": 5,
    "thegatewaypundit.com": 5,
    "zerohedge.com": 5,
}

# Domains known to be government-aligned wire services.
# Sources from these domains are tagged so the judge knows they may just be
# echoing an official press release rather than doing independent reporting.
GOVT_ALIGNED_WIRES = {"pti.in", "ani.in", "dd.news", "pib.gov.in"}

# Multi-region search configurations
# Each region gets its own Google News RSS query so we can detect narrative
# divergence across geographies.
SEARCH_REGIONS = [
    {"label": "India", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
    {"label": "International", "hl": "en-US", "gl": "US", "ceid": "US:en"},
    {"label": "UK/Europe", "hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
]

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


def _get_domain(url: str) -> str:
    """Extract clean domain from a URL."""
    return url.split("//")[-1].split("/")[0].replace("www.", "").lower()


def _get_tier(url: str) -> int:
    """Return the tier for a URL, defaulting to 3 (mainstream)."""
    domain = _get_domain(url)
    if domain in DOMAIN_TIERS:
        return DOMAIN_TIERS[domain]
    parts = domain.split(".")
    if len(parts) > 2:
        parent = ".".join(parts[-2:])
        if parent in DOMAIN_TIERS:
            return DOMAIN_TIERS[parent]
    return 3


def _is_govt_aligned(url: str) -> bool:
    """Check if a domain is a known government-aligned wire service."""
    domain = _get_domain(url)
    if domain in GOVT_ALIGNED_WIRES:
        return True
    parts = domain.split(".")
    if len(parts) > 2:
        parent = ".".join(parts[-2:])
        if parent in GOVT_ALIGNED_WIRES:
            return True
    return False


def _extract_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace to get readable text."""
    html = re.sub(
        r"<(script|style)[^>]*>.*?</(script|style)>",
        " ", html, flags=re.DOTALL | re.IGNORECASE,
    )
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

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------
    async def _scrape_article(self, url: str) -> Optional[str]:
        """Fetch and extract the main text of an article URL."""
        if "news.google.com" in url:
            return None
        try:
            response = await self.scrape_client.get(url)
            if (
                response.status_code == 200
                and "text/html" in response.headers.get("content-type", "")
            ):
                return _extract_text(response.text)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Google News RSS — single region
    # ------------------------------------------------------------------
    async def _fetch_google_news_region(
        self, query: str, region: Dict[str, str], max_results: int
    ) -> List[dict]:
        """Pull headlines from Google News RSS for a specific region."""
        items = []
        try:
            encoded = urllib.parse.quote(query)
            url = (
                f"https://news.google.com/rss/search?q={encoded}"
                f"&hl={region['hl']}&gl={region['gl']}&ceid={region['ceid']}"
            )
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
                    "date": (
                        date_node.text if date_node is not None else "Unknown Date"
                    ),
                    "region": region["label"],
                })
        except Exception as e:
            print(f"Google News RSS error ({region['label']}): {e}")
        return items

    # ------------------------------------------------------------------
    # Multi-region search
    # ------------------------------------------------------------------
    async def _fetch_google_news_multi_region(
        self, query: str, max_per_region: int
    ) -> List[dict]:
        """
        Query Google News RSS across multiple geographic regions concurrently.
        This is the key mechanism for detecting state-controlled narratives:
        if Indian media says X but international media says Y, that divergence
        is itself a powerful signal.
        """
        tasks = [
            self._fetch_google_news_region(query, region, max_per_region)
            for region in SEARCH_REGIONS
        ]
        results = await asyncio.gather(*tasks)
        all_items = []
        for region_items in results:
            all_items.extend(region_items)
        return all_items

    # ------------------------------------------------------------------
    # Google Fact Check Tools API
    # ------------------------------------------------------------------
    async def _fetch_fact_checks(self, query: str, api_key: str) -> List[Source]:
        """
        Query the Google Fact Check Tools API.
        Returns pre-verified claims from IFCN-certified organisations.
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
                print(
                    f"Fact Check API error: {response.status_code} "
                    f"{response.text[:200]}"
                )
                return []
            data = response.json()
            for claim in data.get("claims", []):
                text = claim.get("text", "")
                claimant = claim.get("claimant", "")
                for review in claim.get("claimReview", []):
                    publisher = review.get("publisher", {}).get(
                        "name", "Unknown Fact-Checker"
                    )
                    rating = review.get("textualRating", "Unknown")
                    review_url = review.get("url", "")
                    title = (
                        f'[Tier 2 - IFCN Fact Check] {publisher}: '
                        f'"{text}" → {rating}'
                    )
                    content = (
                        f"URL: {review_url}\n"
                        f"Claim: {text}\n"
                        f"Claimant: {claimant}\n"
                        f"Rating by {publisher}: {rating}"
                    )
                    sources.append(Source(title=title, content=content))
        except Exception as e:
            print(f"Fact Check API exception: {e}")
        return sources

    # ------------------------------------------------------------------
    # Source independence analysis
    # ------------------------------------------------------------------
    def _analyze_source_independence(
        self, items: List[dict]
    ) -> Dict[str, any]:
        """
        Analyze the independence of fetched sources.
        Returns metadata that the judge prompt can use:
        - unique_domains: count of distinct domains
        - region_coverage: which regions returned results
        - govt_aligned_count: how many sources are from govt-aligned wires
        - single_origin_warning: True if most sources trace to the same wire
        """
        domains = set()
        regions = set()
        govt_count = 0
        origin_domains: Dict[str, int] = {}

        for item in items:
            domain = _get_domain(item["url"])
            domains.add(domain)
            regions.add(item.get("region", "Unknown"))
            if _is_govt_aligned(item["url"]):
                govt_count += 1
            origin_domains[domain] = origin_domains.get(domain, 0) + 1

        # Detect if one domain dominates (circular reporting signal)
        max_from_single = max(origin_domains.values()) if origin_domains else 0
        total = len(items) if items else 1
        single_origin_warning = (max_from_single / total) > 0.5

        return {
            "unique_domains": len(domains),
            "region_coverage": sorted(regions),
            "govt_aligned_count": govt_count,
            "govt_aligned_ratio": round(govt_count / total, 2) if total else 0,
            "single_origin_warning": single_origin_warning,
            "dominant_domain": (
                max(origin_domains, key=origin_domains.get)
                if origin_domains
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Main search entry point
    # ------------------------------------------------------------------
    async def search(
        self,
        query: str,
        max_results: int = 5,
        fact_check_api_key: str = "",
    ) -> tuple[List[Source], Dict]:
        """
        Full evidence pipeline:
        1. Fetch headlines from Google News RSS across 3 regions concurrently
        2. Scrape actual article content from top URLs
        3. Analyze source independence (circular reporting detection)
        4. Prepend pre-verified fact-checks from Google Fact Check Tools API

        Returns:
            (sources, independence_meta) — the meta dict is passed to the
            judge prompt so it can reason about source quality.
        """
        max_per_region = max(3, max_results // len(SEARCH_REGIONS))

        # Step 1: Multi-region headline fetch
        raw_items = await self._fetch_google_news_multi_region(
            query, max_per_region
        )

        # Deduplicate by URL
        seen_urls: set = set()
        unique_items: List[dict] = []
        for item in raw_items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                unique_items.append(item)

        # Step 2: Scrape article bodies concurrently
        scrape_tasks = [self._scrape_article(item["url"]) for item in unique_items]
        scraped_bodies = await asyncio.gather(*scrape_tasks)

        sources: List[Source] = []
        for item, body in zip(unique_items, scraped_bodies):
            tier = _get_tier(item["url"])
            region = item.get("region", "Unknown")
            govt_flag = " ⚠GOVT-WIRE" if _is_govt_aligned(item["url"]) else ""
            headline = item["title"]
            date = item["date"]

            if body:
                content = (
                    f"URL: {item['url']}\n"
                    f"Published: {date}\n"
                    f"Region: {region}\n"
                    f"Article excerpt:\n{body}"
                )
            else:
                content = (
                    f"URL: {item['url']}\n"
                    f"Published: {date}\n"
                    f"Region: {region}\n"
                    f"Snippet: {headline}"
                )

            title = f"[Tier {tier}{govt_flag}] [{region}] {headline} ({date})"
            sources.append(Source(title=title, content=content))

        # Step 3: Source independence analysis
        independence_meta = self._analyze_source_independence(unique_items)

        # Step 4: Prepend fact-checks (highest signal)
        fact_check_sources = await self._fetch_fact_checks(
            query, fact_check_api_key
        )

        return fact_check_sources + sources, independence_meta

    async def close(self) -> None:
        await self.search_client.aclose()
        await self.scrape_client.aclose()
