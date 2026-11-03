import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from utils.logger import get_logger

log = get_logger(__name__)

_RETRYABLE = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)

_retry_network_errors = retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)

REQUEST_TIMEOUT_SECONDS = 10


class CurrencyConverter:
    def __init__(self, api_key: str):
        self.base_url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/"

    @_retry_network_errors
    def convert_detailed(self, amount: float, from_currency: str, to_currency: str) -> dict:
        """Convert an amount and return the rate and its publication time, so
        callers can show a quote the traveler is able to cross-check."""
        url = f"{self.base_url}/{from_currency}"
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 200:
            log.warning(
                "currency_api_non_200",
                extra={"from_currency": from_currency, "to_currency": to_currency, "status_code": response.status_code},
            )
            raise ValueError(f"Currency API call failed with status {response.status_code}")
        payload = response.json()
        rates = payload["conversion_rates"]
        if to_currency not in rates:
            raise ValueError(f"{to_currency} not found in exchange rates.")
        return {
            "amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": rates[to_currency],
            "converted": amount * rates[to_currency],
            "rate_published_utc": payload.get("time_last_update_utc"),
            "next_update_utc": payload.get("time_next_update_utc"),
            "source": "exchangerate-api.com (v6 latest)",
        }

    def convert(self, amount: float, from_currency: str, to_currency: str):
        """Convert the amount from one currency to another"""
        return self.convert_detailed(amount, from_currency, to_currency)["converted"]
