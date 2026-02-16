"""Web search tool — Tavily -> Brave -> DuckDuckGo fallback chain.

Uses native tool-calling: the model decides to call web_search,
the orchestrator executes it, and the result goes back as a tool-role
message that the model treats as authoritative state.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from ..config import settings
from .base import BaseTool

# Strip HTML tags from search snippets
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&#x[0-9a-fA-F]+;|&[a-z]+;")

log = logging.getLogger("tools.web_search")

MAX_RESULTS = 5
SNIPPET_MAX_LEN = 500


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = _HTML_TAG_RE.sub("", text)
    text = _HTML_ENTITY_RE.sub("", text)
    return text.strip()


class WebSearchTool(BaseTool):
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information. Use for weather, news, "
            "prices, recent events, or anything requiring up-to-date data."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "Error: no search query provided."

        # Fallback chain: Tavily -> Brave -> DuckDuckGo
        result = None
        if settings.tavily_api_key:
            result = await self._search_tavily(query)
        if result is None and settings.brave_api_key:
            result = await self._search_brave(query)
        if result is None:
            result = await self._search_duckduckgo(query)

        if result is None:
            return f"Web search failed for '{query}'. All search providers returned no results."

        return result

    # ── Tavily ────────────────────────────────────────────────

    async def _search_tavily(self, query: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=settings.search_timeout) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "query": query,
                        "max_results": MAX_RESULTS,
                        "include_answer": True,
                    },
                    headers={
                        "X-API-Key": settings.tavily_api_key,
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            lines = [f"Web search results for '{query}':"]

            # Tavily can return a direct answer — very useful for factual queries
            answer = data.get("answer")
            if answer:
                lines.append(f"Direct answer: {answer}")
                lines.append("")

            results = data.get("results", [])[:MAX_RESULTS]
            if not results and not answer:
                return None

            for i, r in enumerate(results, 1):
                title = _clean_html(r.get("title", "No title"))
                url = r.get("url", "")
                snippet = _clean_html(r.get("content", "") or "")[:SNIPPET_MAX_LEN]
                lines.append(f"{i}. {title} ({url})")
                if snippet:
                    lines.append(f"   {snippet}")

            log.info("Tavily: %d results for '%s'", len(results), query[:60])
            return "\n".join(lines)
        except Exception as e:
            log.warning("Tavily search failed: %s", e)
            return None

    # ── Brave ─────────────────────────────────────────────────

    async def _search_brave(self, query: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=settings.search_timeout) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": MAX_RESULTS},
                    headers={
                        "X-Subscription-Token": settings.brave_api_key,
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            lines = [f"Web search results for '{query}':"]

            # Brave infobox — structured facts (e.g. market cap, population)
            infobox = data.get("infobox", {})
            if infobox:
                title = infobox.get("title", "")
                desc = _clean_html(infobox.get("description", ""))
                if title:
                    lines.append(f"Infobox: {title}")
                if desc:
                    lines.append(f"  {desc[:SNIPPET_MAX_LEN]}")
                for fact in infobox.get("facts", [])[:8]:
                    lines.append(f"  {fact.get('label', '')}: {_clean_html(fact.get('value', ''))}")

            results = data.get("web", {}).get("results", [])[:MAX_RESULTS]
            if not results and not infobox:
                return None

            for i, r in enumerate(results, 1):
                title = _clean_html(r.get("title", "No title"))
                url = r.get("url", "")
                desc = _clean_html(r.get("description", "") or "")[:SNIPPET_MAX_LEN]
                lines.append(f"{i}. {title} ({url})")
                if desc:
                    lines.append(f"   {desc}")
                for extra in (r.get("extra_snippets") or [])[:2]:
                    lines.append(f"   {_clean_html(extra)[:SNIPPET_MAX_LEN]}")

            log.info("Brave: %d results for '%s'", len(results), query[:60])
            return "\n".join(lines)
        except Exception as e:
            log.warning("Brave search failed: %s", e)
            return None

    # ── DuckDuckGo ────────────────────────────────────────────

    async def _search_duckduckgo(self, query: str) -> str | None:
        def _sync():
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    return list(ddgs.text(query, max_results=MAX_RESULTS))
            except Exception as e:
                log.warning("DuckDuckGo search failed: %s", e)
                return []

        raw = await asyncio.get_event_loop().run_in_executor(None, _sync)
        if not raw:
            return None

        lines = [f"Web search results for '{query}':"]
        for i, r in enumerate(raw[:MAX_RESULTS], 1):
            title = _clean_html(r.get("title", "No title"))
            url = r.get("href", r.get("url", ""))
            snippet = _clean_html(r.get("body", "") or "")[:SNIPPET_MAX_LEN]
            lines.append(f"{i}. {title} ({url})")
            if snippet:
                lines.append(f"   {snippet}")

        log.info("DuckDuckGo: %d results for '%s'", len(raw), query[:60])
        return "\n".join(lines)
