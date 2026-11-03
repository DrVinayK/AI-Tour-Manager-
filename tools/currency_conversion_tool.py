import os
from utils.currency_converter import CurrencyConverter
from typing import List
from langchain.tools import tool
from dotenv import load_dotenv

class CurrencyConverterTool:
    def __init__(self):
        load_dotenv()
        self.api_key = os.environ.get("EXCHANGE_RATE_API_KEY")
        self.currency_service = CurrencyConverter(self.api_key)
        self.currency_converter_tool_list = self._setup_tools()

    def _setup_tools(self) -> List:
        """Setup all tools for the currency converter tool"""
        @tool
        def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
            """Convert an amount between currencies at the live rate, and report
            the rate used plus when it was published."""
            quote = self.currency_service.convert_detailed(amount, from_currency, to_currency)
            return (
                f"{quote['amount']} {quote['from_currency']} = "
                f"{quote['converted']:.2f} {quote['to_currency']} "
                f"(rate 1 {quote['from_currency']} = {quote['rate']} {quote['to_currency']}) "
                f"[source: {quote['source']}, rate published {quote['rate_published_utc'] or 'unknown'}]"
            )
        
        return [convert_currency]