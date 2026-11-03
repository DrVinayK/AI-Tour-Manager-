import os
import json
from langchain_tavily import TavilySearch
from langchain_google_community import GooglePlacesTool, GooglePlacesAPIWrapper 

from utils.logger import get_logger

log = get_logger(__name__)

# A denied key or unbilled project fails identically on every call, so once
# we see one there's no point paying the latency on the remaining lookups.
_PERMANENT_FAILURES = ("REQUEST_DENIED", "API key not valid", "billing", "PERMISSION_DENIED")


class GooglePlaceSearchTool:
    def __init__(self, api_key: str):
        # Defer wrapper creation so a missing key doesn't crash construction; callers fall back to Tavily instead.
        self.places_tool = None
        self._disabled_reason = None
        if api_key:
            self.places_wrapper = GooglePlacesAPIWrapper(gplaces_api_key=api_key)
            self.places_tool = GooglePlacesTool(api_wrapper=self.places_wrapper)

    def _require_tool(self) -> GooglePlacesTool:
        if self._disabled_reason:
            raise RuntimeError(self._disabled_reason)
        if self.places_tool is None:
            raise RuntimeError("GPLACES_API_KEY is not configured")
        return self.places_tool

    def _run(self, query: str) -> str:
        tool = self._require_tool()
        try:
            return tool.run(query)
        except Exception as exc:
            message = str(exc)
            if any(marker in message for marker in _PERMANENT_FAILURES):
                self._disabled_reason = (
                    f"Google Places disabled for this run — the API key was rejected "
                    f"(check the key and that billing is enabled): {message}"
                )
                log.warning("google_places_disabled", extra={"error": message})
                raise RuntimeError(self._disabled_reason) from exc
            raise

    def google_search_attractions(self, place: str) -> dict:
        """
        Searches for attractions in the specified place using GooglePlaces API.
        """
        return self._run(f"top attractive places in and around {place}")
    
    def google_search_restaurants(self, place: str) -> dict:
        """
        Searches for available restaurants in the specified place using GooglePlaces API.
        """
        return self._run(f"what are the top 10 restaurants and eateries in and around {place}?")
    
    def google_search_activity(self, place: str) -> dict:
        """
        Searches for popular activities in the specified place using GooglePlaces API.
        """
        return self._run(f"Activities in and around {place}")

    def google_search_transportation(self, place: str) -> dict:
        """
        Searches for available modes of transportation in the specified place using GooglePlaces API.
        """
        return self._run(f"What are the different modes of transportations available in {place}")

class TavilyPlaceSearchTool:
    """Live web search — the only source in this app that can see today.

    Google Places returns identity data only (name, address, phone, website),
    so anything time-sensitive — ticket prices, opening hours, closures,
    festivals, advisories — has to come from here. Searches are recency-
    filtered via `time_range` so Tavily doesn't hand back a five-year-old
    blog post as the current price.
    """

    MAX_SOURCES = 5

    # Recency filtering alone still surfaces reels, video pages and horoscope
    # columns as "sources"; none of them are checkable travel references.
    NOISE_DOMAINS = [
        "instagram.com",
        "facebook.com",
        "x.com",
        "twitter.com",
        "tiktok.com",
        "pinterest.com",
        "youtube.com",
    ]

    def __init__(self):
        pass

    def _search(self, query: str, time_range: str = "year", topic: str = "general"):
        tavily_tool = TavilySearch(
            topic=topic,
            include_answer="advanced",
            search_depth="advanced",
            time_range=time_range,
            max_results=self.MAX_SOURCES,
            exclude_domains=self.NOISE_DOMAINS,
        )
        result = tavily_tool.invoke({"query": query})
        if not isinstance(result, dict):
            return result

        answer = result.get("answer")
        if not answer:
            return result

        sources = []
        for item in (result.get("results") or [])[: self.MAX_SOURCES]:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            sources.append(
                {
                    "title": item.get("title") or item["url"],
                    "url": item["url"],
                    "published_date": item.get("published_date"),
                }
            )
        return {"answer": answer, "sources": sources}

    def tavily_search_attractions(self, place: str) -> dict:
        """
        Searches for attractions in the specified place using TavilySearch.
        """
        return self._search(f"top attractive places in and around {place} with current entry fees and opening hours")

    def tavily_search_restaurants(self, place: str) -> dict:
        """
        Searches for available restaurants in the specified place using TavilySearch.
        """
        return self._search(
            f"what are the top 10 restaurants and eateries in and around {place} and their current price range"
        )

    def tavily_search_activity(self, place: str) -> dict:
        """
        Searches for popular activities in the specified place using TavilySearch.
        """
        return self._search(f"activities in and around {place} with current ticket prices and timings")

    def tavily_search_transportation(self, place: str) -> dict:
        """
        Searches for available modes of transportation in the specified place using TavilySearch.
        """
        return self._search(
            f"What are the different modes of transportations available in {place} and their current fares"
        )

    def tavily_search_current_events(self, place: str, travel_period: str = "") -> dict:
        """Recent news affecting a trip: closures, festivals, strikes, advisories."""
        window = f" during {travel_period}" if travel_period else ""
        return self._search(
            f"{place} travel news{window}: festivals, events, attraction closures, "
            "strikes, weather disruption, entry or visa rule changes",
            time_range="week",
            topic="news",
        )

    def tavily_search_live_prices(self, place: str, item: str) -> dict:
        """Current price/hours for one specific thing, restricted to recent pages."""
        return self._search(
            f"{item} in {place}: current price, entry fee and opening hours",
            time_range="month",
        )

