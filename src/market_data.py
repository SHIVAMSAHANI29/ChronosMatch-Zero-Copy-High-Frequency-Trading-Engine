
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.twelvedata.com"


async def get_stock_price(symbol: str):
    api_key = os.getenv("TWELVE_DATA_API_KEY")

    if not api_key:
        raise ValueError("TWELVE_DATA_API_KEY is missing from .env")

    params = {
        "symbol": symbol.upper(),
        "exchange": "NSE",
        "apikey": api_key
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BASE_URL}/price",
            params=params
        )

        response.raise_for_status()
        data = response.json()

    if "price" not in data:
        raise ValueError(data.get("message", "Price unavailable"))

    return {
        "symbol": symbol.upper(),
        "price": float(data["price"]),
        "source": "Twelve Data"
    }
