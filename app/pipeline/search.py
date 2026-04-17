from typing import List, Dict, Any
import httpx
import xml.etree.ElementTree as ET
import urllib.parse
from app.models.responses import Source

# Simple mapping of Indian/Global domains to Tier scores. 
# Tier 1 = Highly Reliable Wire Services
# Tier 2 = Specialized Fact Checkers
# Tier 3 = Mainstream News (varying bias)
# Tier 4 = Ideological/Opinion Blogs
DOMAIN_TIERS = {
    "reuters.com": 1,
    "apnews.com": 1,
    "bbc.com": 1,
    "altnews.in": 2,
    "boomlive.in": 2,
    "thehindu.com": 3,
    "indianexpress.com": 3,
    "ndtv.com": 3,
    "timesofindia.indiatimes.com": 3,
    "opindia.com": 4,
    "thewire.in": 4,
    "swarajyamag.com": 4,
}

class LiveSearchModule:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def search(self, query: str, max_results: int = 5) -> List[Source]:
        """
        Uses Google News RSS to aggressively pull live search results for a claim.
        Bypasses typical rate limits. Returns a list of Source objects with tagged tiers.
        """
        sources = []
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
            
            response = await self.client.get(url)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            
            for item in root.findall('./channel/item')[:max_results]:
                title_node = item.find('title')
                link_node = item.find('link')
                date_node = item.find('pubDate')
                
                if title_node is None or link_node is None:
                    continue
                    
                title_str = title_node.text
                link_str = link_node.text
                date_str = date_node.text if date_node is not None else "Unknown Date"
                
                domain = link_str.split("//")[-1].split("/")[0].replace("www.", "")
                tier = DOMAIN_TIERS.get(domain, 3)
                
                title = f"[Tier {tier}] {title_str} ({date_str})"
                content = f"URL: {link_str}\nSnippet: {title_str}"
                
                sources.append(Source(title=title, content=content))
                    
        except Exception as e:
            print(f"Live Search RSS error: {e}")
            
        return sources
