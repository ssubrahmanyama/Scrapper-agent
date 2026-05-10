"""
services/crawler/searxng_search.py
Replaces Google Custom Search API with self-hosted SearXNG (AGPL-3.0).
SearXNG is deployed as a container in docker-compose / Kubernetes.
"""
from __future__ import annotations
import asyncio
from typing import Dict, List, Optional
from urllib.parse import quote, urlparse
import httpx, structlog, re

logger = structlog.get_logger(__name__)

# SearXNG runs as internal service — no external API key needed
SEARXNG_BASE = "http://searxng:8080"   # docker-compose service name
REQUEST_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
BLOCKED_IP = re.compile(r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|169\.254\.)", re.I)


def _is_safe_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme != "https":
        return False
    if BLOCKED_IP.match(p.hostname or ""):
        return False
    return True


class SearXNGSearchService:
    """Async wrapper around the SearXNG JSON API."""

    def __init__(self, base_url: str = SEARXNG_BASE):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True)
        return self._client

    async def search(self, query: str, num_results: int = 10) -> List[Dict]:
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json", "engines": "google,bing,duckduckgo", "language": "en"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("SearXNG query failed", query=query, error=str(e))
            return []

        results = resp.json().get("results", [])
        return [
            {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("content", ""), "display_link": urlparse(r.get("url","")).netloc}
            for r in results
            if r.get("url", "").startswith("https://") and _is_safe_url(r.get("url",""))
        ][:num_results]

    async def search_all_pages(self, query: str, max_results: int = 50) -> List[Dict]:
        results: List[Dict] = []
        pageno = 1
        while len(results) < max_results:
            client = await self._get_client()
            try:
                resp = await client.get(
                    f"{self.base_url}/search",
                    params={"q": query, "format": "json", "pageno": pageno, "engines": "google,bing,duckduckgo"},
                )
                batch = resp.json().get("results", [])
                if not batch:
                    break
                results.extend([r for r in batch if r.get("url","").startswith("https://")])
                pageno += 1
                await asyncio.sleep(0.3)
            except Exception:
                break
        return results[:max_results]

    async def close(self):
        if self._client:
            await self._client.aclose()


class PageFetcher:
    """Async HTTP fetcher — SSRF-safe, 1 MB cap."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": "PrivacyShieldBot/1.0 (+https://privacyshield.local/bot)"},
                timeout=REQUEST_TIMEOUT, follow_redirects=True, max_redirects=3,
            )
        return self._client

    async def fetch(self, url: str) -> Optional[str]:
        if not _is_safe_url(url):
            return None
        client = await self._get_client()
        try:
            chunks, total = [], 0
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                async for chunk in resp.aiter_bytes(65536):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > 1_048_576:
                        break
            return b"".join(chunks).decode("utf-8", errors="replace")
        except Exception:
            return None

    async def fetch_many(self, urls: List[str], concurrency: int = 5) -> Dict[str, str]:
        sem = asyncio.Semaphore(concurrency)
        results: Dict[str, str] = {}

        async def _one(url: str):
            async with sem:
                c = await self.fetch(url)
                if c:
                    results[url] = c

        await asyncio.gather(*[_one(u) for u in urls])
        return results

    async def close(self):
        if self._client:
            await self._client.aclose()


class DataBrokerScanner:
    def build_search_queries(self, name: str, location: str | None = None) -> List[str]:
        safe = re.sub(r"[^\w\s]", "", name)[:100]
        queries = [
            f'"{safe}" site:spokeo.com',
            f'"{safe}" site:whitepages.com',
            f'"{safe}" site:radaris.com',
            f'"{safe}" site:intelius.com',
            f'"{safe}" site:beenverified.com',
            f'"{safe}" personal information address phone',
            f'"{safe}" profile contact details',
        ]
        if location:
            loc = re.sub(r"[^\w\s,]", "", location)[:50]
            queries.append(f'"{safe}" "{loc}" contact')
        return queries

    async def generate_urls(self, target_name: str, search_service: SearXNGSearchService, location: str | None = None) -> List[str]:
        urls: List[str] = []
        for q in self.build_search_queries(target_name, location):
            results = await search_service.search(q, num_results=5)
            urls.extend(r["url"] for r in results)
            await asyncio.sleep(0.3)
        return list(dict.fromkeys(urls))


# Singletons
searxng_service = SearXNGSearchService()
page_fetcher = PageFetcher()
data_broker_scanner = DataBrokerScanner()
