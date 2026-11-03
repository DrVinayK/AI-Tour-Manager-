import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import List

from langchain.tools import tool
from dotenv import load_dotenv

from utils.weather_info import WeatherForecastTool


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class WeatherInfoTool:
    def __init__(self):
        load_dotenv()
        self.api_key = os.environ.get("OPENWEATHERMAP_API_KEY")
        self.weather_service = WeatherForecastTool(self.api_key)
        self.weather_tool_list = self._setup_tools()
    
    def _setup_tools(self) -> List:
        """Setup all tools for the weather forecast tool"""
        @tool
        def get_current_weather(city: str) -> str:
            """Get the live observed weather for a city, with observation time."""
            weather_data = self.weather_service.get_current_weather(city)
            if not weather_data:
                return f"Could not fetch weather for {city}"

            main = weather_data.get("main", {})
            desc = weather_data.get("weather", [{}])[0].get("description", "N/A")
            observed_ts = weather_data.get("dt")
            observed = (
                datetime.fromtimestamp(observed_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                if observed_ts
                else "unknown time"
            )
            return (
                f"Current weather in {city}: {main.get('temp', 'N/A')}°C "
                f"(feels like {main.get('feels_like', 'N/A')}°C), {desc}, "
                f"humidity {main.get('humidity', 'N/A')}%, "
                f"wind {weather_data.get('wind', {}).get('speed', 'N/A')} m/s. "
                f"[source: OpenWeatherMap current-weather API, observed {observed}, fetched {_now_utc()}]"
            )
        
        @tool
        def get_weather_forecast(city: str) -> str:
            """Get the 5-day forecast for a city, summarised per calendar day."""
            forecast_data = self.weather_service.get_forecast_weather(city)
            if not forecast_data or "list" not in forecast_data:
                return f"Could not fetch forecast for {city}"

            by_day = defaultdict(lambda: {"temps": [], "conditions": []})
            for item in forecast_data["list"]:
                date = item["dt_txt"].split(" ")[0]
                by_day[date]["temps"].append(item["main"]["temp"])
                by_day[date]["conditions"].append(item["weather"][0]["description"])

            lines = []
            for date in sorted(by_day):
                day = by_day[date]
                dominant = max(set(day["conditions"]), key=day["conditions"].count)
                lines.append(
                    f"{date}: low {min(day['temps']):.0f}°C / high {max(day['temps']):.0f}°C, mostly {dominant}"
                )

            return (
                f"Weather forecast for {city} "
                f"[source: OpenWeatherMap 5-day/3-hour forecast API, fetched {_now_utc()}]:\n"
                + "\n".join(lines)
                + "\nNote: this API only covers the next 5 days; anything beyond that is a seasonal average, not a forecast."
            )
    
        return [get_current_weather, get_weather_forecast]