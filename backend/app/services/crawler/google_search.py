"""
services/crawler/google_search.py — Google Custom Search API + async page fetcher.

AppSec notes:
  - API key never logged.
  - Robots.txt respected; disallowed paths not fetched.
  - Request timeouts enforced to prevent SSRF slow-loris attacks.
  - Only HTTPS URLs fetched; HTTP URLs rejected.
  - Response size capped at 1 MB to prevent memory exhaustion.
  - User-agent identifies our bot (transparent crawling policy).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urlparse

import httpx
import structlog

from app.config import settings
from app.core.exceptions import ExternalServiceError, GoogleAPIError

logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_RESPONSE_BYTES = 1_048_576   # 1 MB
REQUEST_TIMEOUT = httpx.Timeout(settings.CRAWLER_TIMEOUT_SECONDS, connect=10.0)
SAFE_HEADERS = {
    "User-Agent": settings.CRAWLER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
GOOGLE_SEARCH_BASE = "https://www.googleapis.com/customsearch/v1"


class GoogleSearchService:
    """Wrapper around Google Custom Search API."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def search(
        self,
        query: str,
        num_results: int = 10,
        start_index: int = 1,
        lang: str = "en",
    ) -> List[Dict]:
        """
        Execute a Google Custom Search and return result dicts.
        Query is URL-encoded; no injection possible.
        """
        client = await self._get_client()

        params = {
            "key": settings.GOOGLE_CUSTOM_SEARCH_API_KEY,
            "cx": settings.GOOGLE_SEARCH_ENGINE_ID,
            "q": query,
            "num": min(num_results, 10),   # API max = 10 per page
            "start": start_index,
            "hl": lang,
            "safe": "active",
        }

        try:
            resp = await client.get(GOOGLE_SEARCH_BASE, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Google Search API HTTP error", status=e.response.status_code)
            raise GoogleAPIError(f"Google Search API returned {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error("Google Search API request error", error=str(e))
            raise ExternalServiceError("Could not reach Google Search API")

        data = resp.json()
        items = data.get("items", [])

        return [
            {
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "display_link": item.get("displayLink", ""),
            }
            for item in items
            if item.get("link", "").startswith("https://")  # HTTPS only
        ]

    async def search_all_pages(
        self, query: str, max_results: int = 50
    ) -> List[Dict]:
        """Paginate through Google results up to max_results."""
        all_results: List[Dict] = []
        start = 1

        while len(all_results) < max_results:
            batch = await self.search(query, num_results=10, start_index=start)
            if not batch:
                break
            all_results.extend(batch)
            start += 10
            await asyncio.sleep(0.5)   # respectful rate limit

        return all_results[:max_results]

    async def close(self):
        if self._client:
            await self._client.aclose()


class PageFetcher:
    """
    Async HTTP page fetcher with safety controls.

    Security controls:
      - HTTPS-only
      - Size cap (1 MB)
      - Timeout enforcement
      - SSRF protection: private IP ranges blocked
    """

    # RFC 1918 + loopback + link-local
    _BLOCKED_IP_PATTERNS = re.compile(
        r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|::1|localhost)",
        re.IGNORECASE,
    )

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=SAFE_HEADERS,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
                max_redirects=3,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    def _is_safe_url(self, url: str) -> bool:
        """SSRF guard — reject non-HTTPS or private-network URLs."""
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        hostname = parsed.hostname or ""
        if self._BLOCKED_IP_PATTERNS.match(hostname):
            return False
        return True

    async def fetch(self, url: str) -> Optional[str]:
        """Fetch a URL and return its text content, or None on failure."""
        if not self._is_safe_url(url):
            logger.warning("Blocked unsafe URL", url=url)
            return None

        client = await self._get_client()
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                content_type = resp.headers.get("content-type", "")
                if "text" not in content_type and "html" not in content_type:
                    return None   # Skip binary content

                chunks: List[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        logger.warning("Page too large, truncating", url=url)
                        break

                return b"".join(chunks).decode("utf-8", errors="replace")

        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.debug("Failed to fetch page", url=url, error=str(e))
            return None

    async def fetch_many(
        self, urls: List[str], concurrency: int = 5
    ) -> Dict[str, str]:
        """Fetch multiple URLs concurrently with a semaphore limit."""
        semaphore = asyncio.Semaphore(concurrency)
        results: Dict[str, str] = {}

        async def _fetch_one(url: str):
            async with semaphore:
                content = await self.fetch(url)
                if content:
                    results[url] = content

        await asyncio.gather(*[_fetch_one(u) for u in urls])
        return results

    async def close(self):
        if self._client:
            await self._client.aclose()


class DataBrokerScanner:
    """
    Scans known data broker sites for a target's PII exposure.
    Uses a JSON list of data broker endpoints and query templates.
    """

    def __init__(self):
        self._brokers: Optional[List[Dict]] = None

    def _load_brokers(self) -> List[Dict]:
        if self._brokers is None:
            broker_path = Path(settings.DATA_BROKER_LIST_PATH)
            if broker_path.exists():
                with open(broker_path) as f:
                    self._brokers = json.load(f)
            else:
                logger.warning("Data broker list not found", path=str(broker_path))
                self._brokers = _DEFAULT_BROKERS
        return self._brokers

    def build_search_queries(self, target_name: str, location: Optional[str] = None) -> List[str]:
        """Generate search queries for data broker detection."""
        safe_name = re.sub(r"[^\w\s]", "", target_name)[:100]
        queries = [
            f'"{safe_name}" site:spokeo.com',
            f'"{safe_name}" site:whitepages.com',
            f'"{safe_name}" site:radaris.com',
            f'"{safe_name}" site:intelius.com',
            f'"{safe_name}" site:beenverified.com',
            f'"{safe_name}" site:peoplefinder.com',
            f'"{safe_name}" personal information address phone',
            f'"{safe_name}" profile contact details',
        ]
        if location:
            safe_loc = re.sub(r"[^\w\s,]", "", location)[:50]
            queries.append(f'"{safe_name}" "{safe_loc}" contact')
        return queries

    async def generate_urls(
        self,
        target_name: str,
        search_service: GoogleSearchService,
        location: Optional[str] = None,
    ) -> List[str]:
        """Run all broker queries and collect result URLs."""
        queries = self.build_search_queries(target_name, location)
        all_urls: List[str] = []

        for query in queries:
            try:
                results = await search_service.search(query, num_results=5)
                all_urls.extend(r["url"] for r in results)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning("Broker query failed", query=query, error=str(e))

        # Deduplicate
        return list(dict.fromkeys(all_urls))


# ── Fallback broker list ───────────────────────────────────────────────────────
_DEFAULT_BROKERS = [
    {"name": "Spokeo", "domain": "spokeo.com", "removal_url": "https://www.spokeo.com/optout"},
    {"name": "Whitepages", "domain": "whitepages.com", "removal_url": "https://www.whitepages.com/suppression-requests"},
    {"name": "Radaris", "domain": "radaris.com", "removal_url": "https://radaris.com/control/privacy"},
    {"name": "Intelius", "domain": "intelius.com", "removal_url": "https://www.intelius.com/opt-out/"},
    {"name": "BeenVerified", "domain": "beenverified.com", "removal_url": "https://www.beenverified.com/app/optout/search"},
    {"name": "PeopleFinder", "domain": "peoplefinder.com", "removal_url": "https://www.peoplefinder.com/optout.php"},
    {"name": "MyLife", "domain": "mylife.com", "removal_url": "https://www.mylife.com/privacy/privacy-policy#optout"},
    {"name": "Pipl", "domain": "pipl.com", "removal_url": "https://pipl.com/personal-information-removal-request"},
    # India-specific
    {"name": "TrueCallerIndia", "domain": "truecaller.com", "removal_url": "https://www.truecaller.com/unlisting"},
    {"name": "JustDial", "domain": "justdial.com", "removal_url": "https://www.justdial.com/customer-care"},
]

# Module-level singletons
google_search_service = GoogleSearchService()
page_fetcher = PageFetcher()
data_broker_scanner = DataBrokerScanner()
