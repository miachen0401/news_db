"""Polygon.io news fetcher."""
from typing import List
from datetime import datetime, timedelta
import httpx

from models.raw_news import RawNewsItem


class PolygonClient:
    """Polygon.io API client."""

    def __init__(self, api_key: str):
        """
        Initialize Polygon client.

        Args:
            api_key: Polygon.io API key
        """
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_ticker_news(
        self,
        ticker: str,
        published_utc_gte: str,
        published_utc_lte: str,
        limit: int = 50
    ):
        """
        Get news for a specific ticker.

        Args:
            ticker: Stock ticker symbol
            published_utc_gte: Start date (YYYY-MM-DD)
            published_utc_lte: End date (YYYY-MM-DD)
            limit: Maximum number of results (default 50, max 1000)

        Returns:
            List of news articles
        """
        response = await self.client.get(
            f"{self.base_url}/v2/reference/news",
            params={
                "ticker": ticker.upper(),
                "published_utc.gte": published_utc_gte,
                "published_utc.lte": published_utc_lte,
                "limit": limit,
                "apiKey": self.api_key
            }
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            # Transform Polygon format to standardized format
            articles = []
            for article in results:
                articles.append({
                    "id": article.get("id", ""),
                    "title": article.get("title", ""),
                    "description": article.get("description", ""),
                    "url": article.get("article_url", ""),
                    "published_utc": article.get("published_utc", ""),
                    "author": article.get("author", ""),
                    "publisher": article.get("publisher", {}).get("name", ""),
                    "image_url": article.get("image_url", ""),
                    "tickers": article.get("tickers", []),
                    "amp_url": article.get("amp_url", ""),
                })

            return articles

        elif response.status_code == 429:
            print(f"⚠️  Polygon rate limit exceeded")
            return []
        else:
            print(f"⚠️  Polygon API error: {response.status_code}")
            return []

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class PolygonNewsFetcher:
    """Fetcher for Polygon.io news API."""

    def __init__(self, api_key: str):
        """
        Initialize Polygon fetcher.

        Args:
            api_key: Polygon.io API key
        """
        self.client = PolygonClient(api_key=api_key)

    async def fetch_for_symbol(
        self,
        symbol: str,
        days_back: int = 7,
        limit: int = 50
    ) -> List[RawNewsItem]:
        """
        Fetch news for a single symbol.

        Args:
            symbol: Stock ticker symbol
            days_back: Number of days to fetch (default 7)
            limit: Maximum number of articles (default 50, max 1000)

        Returns:
            List of RawNewsItem objects
        """
        try:
            # Calculate date range
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days_back)

            # Format dates for Polygon API (YYYY-MM-DD)
            from_str = from_date.strftime("%Y-%m-%d")
            to_str = to_date.strftime("%Y-%m-%d")

            print(f"🔍 Fetching Polygon news for {symbol} ({from_str} to {to_str})...")

            # Fetch from Polygon
            articles = await self.client.get_ticker_news(
                ticker=symbol,
                published_utc_gte=from_str,
                published_utc_lte=to_str,
                limit=limit
            )

            # Convert to RawNewsItem objects
            raw_items = []
            for article in articles:
                try:
                    raw_item = RawNewsItem.from_polygon_response(
                        symbol=symbol,
                        article_data=article
                    )
                    raw_items.append(raw_item)
                except Exception as e:
                    print(f"⚠️  Error converting article: {e}")
                    continue

            print(f"✅ Fetched {len(raw_items)} articles for {symbol} from Polygon")
            return raw_items

        except Exception as e:
            print(f"❌ Error fetching Polygon news for {symbol}: {e}")
            return []

    async def fetch_for_symbols(
        self,
        symbols: List[str],
        days_back: int = 7,
        limit: int = 50
    ) -> List[RawNewsItem]:
        """
        Fetch news for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            days_back: Number of days to fetch
            limit: Maximum number of articles per symbol

        Returns:
            List of RawNewsItem objects for all symbols
        """
        all_items = []

        for symbol in symbols:
            items = await self.fetch_for_symbol(symbol, days_back, limit)
            all_items.extend(items)

            # Polygon has rate limits (5 requests/minute for free tier)
            # Add a small delay between requests
            import asyncio
            await asyncio.sleep(0.2)  # 200ms delay

        print(f"📊 Total fetched: {len(all_items)} articles for {len(symbols)} symbols")
        return all_items

    async def close(self):
        """Close the Polygon client."""
        await self.client.close()
