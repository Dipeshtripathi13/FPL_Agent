"""Brave Search API adapter for source discovery, not fact extraction."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from fpl_agent.evidence import detect_prompt_injection
from fpl_agent.providers.base import ProviderDocument
from fpl_agent.providers.cache import SearchCache
from fpl_agent.source_policy import is_blocked_game_domain

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    """Discover sources through Brave's licensed API with fail-closed domain filtering."""

    name = "brave"

    def __init__(
        self,
        api_key: str,
        allowed_domains: list[str],
        *,
        cache: SearchCache | None = None,
        freshness: str = "pw",
        country: str = "GB",
        search_language: str = "en",
        min_interval_seconds: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("A Brave Search API key is required")
        normalized = {domain.casefold().strip(". ") for domain in allowed_domains if domain.strip()}
        if not normalized:
            raise ValueError("At least one reviewed --allowed-domain is required")
        blocked = {domain for domain in normalized if is_blocked_game_domain(domain)}
        if blocked:
            raise ValueError(
                "Automated FPL game domains are blocked by project policy: "
                + ", ".join(sorted(blocked))
            )
        self.api_key = api_key
        self.allowed_domains = normalized
        self.cache = cache
        self.freshness = freshness
        self.country = country
        self.search_language = search_language
        self.min_interval_seconds = max(0, min_interval_seconds)
        self.client = client
        self._last_request_at = 0.0

    def search(self, query: str, max_results: int = 5) -> list[ProviderDocument]:
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        domain_filter = " OR ".join(f"site:{domain}" for domain in sorted(self.allowed_domains))
        bounded_query = f"{query} ({domain_filter})"
        if len(bounded_query) > 600 or len(bounded_query.split()) > 75:
            raise ValueError("Search query exceeds Brave's documented limit")
        if not 1 <= max_results <= 20:
            raise ValueError("max_results must be between 1 and 20")
        request = {
            "q": bounded_query,
            "count": max_results,
            "freshness": self.freshness,
            "country": self.country,
            "search_lang": self.search_language,
            "safesearch": "strict",
            "allowed_domains": sorted(self.allowed_domains),
        }
        if self.cache and (cached := self.cache.get(self.name, request)) is not None:
            return [ProviderDocument.model_validate(item) for item in cached]

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        documents = self._request(request)
        self._last_request_at = time.monotonic()
        if self.cache:
            self.cache.put(
                self.name,
                request,
                [document.model_dump(mode="json") for document in documents],
            )
        return documents

    def _request(self, request: dict[str, object]) -> list[ProviderDocument]:
        params = {key: value for key, value in request.items() if key != "allowed_domains"}
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        if self.client is not None:
            response = self.client.get(BRAVE_SEARCH_URL, params=params, headers=headers)
        else:
            with httpx.Client(timeout=20) as client:
                response = client.get(BRAVE_SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        retrieved_at = datetime.now(UTC)
        results = response.json().get("web", {}).get("results", [])
        documents: list[ProviderDocument] = []
        for item in results:
            url = str(item.get("url", ""))
            if not self._domain_is_allowed(url):
                continue
            title = str(item.get("title", ""))
            snippet = str(item.get("description", ""))
            flags = detect_prompt_injection(f"{title}\n{snippet}")
            documents.append(
                ProviderDocument(
                    provider=self.name,
                    title=title,
                    url=url,
                    snippet=snippet,
                    published_at=self._parse_timestamp(item.get("page_age")),
                    retrieved_at=retrieved_at,
                    safety_flags=flags,
                )
            )
        return documents

    def _domain_is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        hostname = parsed.hostname.casefold().strip(".")
        if is_blocked_game_domain(hostname):
            return False
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.allowed_domains
        )

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
