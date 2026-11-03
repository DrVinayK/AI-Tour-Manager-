import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from utils.logger import get_logger

log = get_logger(__name__)

# Network-level failures are worth retrying (the API might just be
# momentarily slow/unreachable); a 4xx/5xx JSON body is not retried here —
# that's a real API response, and get_current_weather/get_forecast_weather
# already treat any non-200 as "no data" rather than raising.
_RETRYABLE = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)

_retry_network_errors = retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)

REQUEST_TIMEOUT_SECONDS = 10


class WeatherForecastTool:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"

    @_retry_network_errors
    def get_current_weather(self, place: str):
        """Get current weather of a place"""
        url = f"{self.base_url}/weather"
        params = {
            "q": place,
            "appid": self.api_key,
            "units": "metric",  # without this OpenWeatherMap returns Kelvin
        }
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 200:
            log.warning("weather_api_non_200", extra={"place": place, "status_code": response.status_code})
            return {}
        return response.json()

    @_retry_network_errors
    def get_forecast_weather(self, place: str):
        """Get weather forecast of a place"""
        url = f"{self.base_url}/forecast"
        params = {
            "q": place,
            "appid": self.api_key,
            "cnt": 40,  # full 5-day / 3-hour window so multi-day trips are covered
            "units": "metric",
        }
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 200:
            log.warning("weather_api_non_200", extra={"place": place, "status_code": response.status_code})
            return {}
        return response.json()
