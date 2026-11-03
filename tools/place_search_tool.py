"""Place-research tools.

Two providers with different jobs, queried together rather than as a
primary/fallback pair:

* Google Places gives *identity* only — name, address, phone, website. It
  carries nothing time-sensitive, so on its own it cannot make a plan
  current.
* Tavily is recency-filtered live web search, and is the only source here
  that can see today's prices, hours, closures and events.

Both are stamped with provider and fetch time so the itinerary can cite
something the traveler is able to open and cross-check.
"""

import os
from datetime import datetime, timezone
from typing import List

from langchain.tools import tool
from dotenv import load_dotenv

from utils.place_info_search import GooglePlaceSearchTool, TavilyPlaceSearchTool


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_sourced(result) -> str:
    """Render a Tavily payload so its source links survive into the plan."""
    if not isinstance(result, dict) or "answer" not in result:
        return str(result)

    lines = [str(result["answer"])]
    sources = result.get("sources") or []
    if sources:
        lines.append("Sources:")
        for src in sources:
            published = f" (published {src['published_date']})" if src.get("published_date") else ""
            lines.append(f"- {src['title']}: {src['url']}{published}")
    return "\n".join(lines)


class PlaceSearchTool:
    def __init__(self):
        load_dotenv()
        self.google_api_key = os.environ.get("GPLACES_API_KEY")
        self.google_places_search = GooglePlaceSearchTool(self.google_api_key)
        self.tavily_search = TavilyPlaceSearchTool()
        self.place_search_tool_list = self._setup_tools()

    def _lookup(self, place: str, label: str, google_fn, tavily_fn) -> str:
        """Query both providers and label each block, so the agent can tell
        verified identity data apart from live-but-web-sourced detail."""
        fetched_at = _now_utc()
        blocks = [f"{label} in and around {place} (fetched {fetched_at}):"]

        try:
            google_result = google_fn(place)
        except Exception as exc:
            google_result = None
            blocks.append(f"[Google Places unavailable: {exc}]")
        if google_result:
            blocks.append(
                "-- Verified listings (Google Places API: names, addresses, phone, "
                f"website; contains NO prices or opening hours) --\n{google_result}"
            )

        try:
            tavily_result = tavily_fn(place)
            blocks.append(
                "-- Current web research (Tavily, recency-filtered; use this for "
                f"today's prices/hours/conditions) --\n{_format_sourced(tavily_result)}"
            )
        except Exception as exc:
            blocks.append(
                f"[Live web search unavailable: {exc}. No current pricing or hours "
                "could be verified — mark such details as unverified estimates.]"
            )

        return "\n\n".join(blocks)

    def _setup_tools(self) -> List:
        """Setup all tools for the place search tool"""

        @tool
        def search_attractions(place: str) -> str:
            """Search attractions of a place: verified listings plus current web research."""
            return self._lookup(
                place,
                "Attractions",
                self.google_places_search.google_search_attractions,
                self.tavily_search.tavily_search_attractions,
            )

        @tool
        def search_restaurants(place: str) -> str:
            """Search restaurants of a place: verified listings plus current web research."""
            return self._lookup(
                place,
                "Restaurants",
                self.google_places_search.google_search_restaurants,
                self.tavily_search.tavily_search_restaurants,
            )

        @tool
        def search_activities(place: str) -> str:
            """Search activities of a place: verified listings plus current web research."""
            return self._lookup(
                place,
                "Activities",
                self.google_places_search.google_search_activity,
                self.tavily_search.tavily_search_activity,
            )

        @tool
        def search_transportation(place: str) -> str:
            """Search transportation options of a place, with current fares where available."""
            return self._lookup(
                place,
                "Local transportation options",
                self.google_places_search.google_search_transportation,
                self.tavily_search.tavily_search_transportation,
            )

        @tool
        def search_current_events(place: str, travel_period: str = "") -> str:
            """Check the last week's travel news for a place: festivals, closures,
            strikes, disruption and entry-rule changes. Use this for anything
            that could have changed recently."""
            fetched_at = _now_utc()
            try:
                result = self.tavily_search.tavily_search_current_events(place, travel_period)
            except Exception as exc:
                return f"Current events for {place} could not be retrieved ({exc}). Do not assume conditions are normal — tell the traveler to check locally."
            return (
                f"Recent travel news for {place} "
                f"[source: Tavily news search, last 7 days, fetched {fetched_at}]:\n"
                f"{_format_sourced(result)}"
            )

        @tool
        def search_live_price(place: str, item: str) -> str:
            """Look up the current price and opening hours of one specific
            attraction, tour, pass or transport ticket. Use this instead of
            recalling a price from memory."""
            fetched_at = _now_utc()
            try:
                result = self.tavily_search.tavily_search_live_prices(place, item)
            except Exception as exc:
                return f"Live price for '{item}' in {place} unavailable ({exc}). Mark any figure you give as an unverified estimate."
            return (
                f"Current pricing for '{item}' in {place} "
                f"[source: Tavily web search, last 30 days, fetched {fetched_at}]:\n"
                f"{_format_sourced(result)}"
            )

        return [
            search_attractions,
            search_restaurants,
            search_activities,
            search_transportation,
            search_current_events,
            search_live_price,
        ]