"""General news fetcher without symbol filtering."""
from typing import List, Dict, Any
from datetime import datetime, timedelta
import httpx

from models.raw_news import RawNewsItem


class GeneralNewsFetcher:
    """Fetches general market news without symbol filtering."""

    def __init__(self, finnhub_api_key: str, polygon_api_key: str):
        """
        Initialize general news fetcher.

        Args:
            finnhub_api_key: Finnhub API key
            polygon_api_key: Polygon API key
        """
        self.finnhub_api_key = finnhub_api_key
        self.polygon_api_key = polygon_api_key
        self.finnhub_client = httpx.AsyncClient(timeout=30.0)
        self.polygon_client = httpx.AsyncClient(timeout=30.0)

    async def fetch_finnhub_general_news(
        self,
        category: str = "general",
        min_id: int = 0,
        after_timestamp: datetime = None
    ) -> List[RawNewsItem]:
        """
        Fetch general market news from Finnhub.

        Note: Finnhub API always returns latest 100 articles, doesn't support date filtering.
        We filter client-side using after_timestamp.

        Args:
            category: News category (general, forex, crypto, merger)
            min_id: Minimum news ID for pagination
            after_timestamp: Only return news published after this time (client-side filter)

        Returns:
            List of RawNewsItem objects
        """
        try:
            print(f"🔍 Fetching Finnhub general news (category: {category})...")

            response = await self.finnhub_client.get(
                "https://finnhub.io/api/v1/news",
                params={
                    "category": category,
                    "minId": min_id,
                    "token": self.finnhub_api_key
                }
            )

            if response.status_code == 200:
                articles = response.json()

                raw_items = []
                for article in articles:
                    try:
                        # Use factory method to create RawNewsItem (extracts published_at)
                        raw_item = RawNewsItem.from_finnhub_response(
                            symbol="GENERAL",
                            article_data=article
                        )

                        # Client-side filtering: only include news after timestamp
                        if after_timestamp and raw_item.published_at:
                            # Strip timezone for comparison
                            item_time = raw_item.published_at.replace(tzinfo=None) if raw_item.published_at.tzinfo else raw_item.published_at
                            filter_time = after_timestamp.replace(tzinfo=None) if after_timestamp.tzinfo else after_timestamp

                            if item_time <= filter_time:
                                continue  # Skip this article (too old)

                        raw_items.append(raw_item)
                    except Exception as e:
                        print(f"⚠️  Error converting article: {e}")
                        continue

                print(f"✅ Fetched {len(raw_items)} general news from Finnhub")
                if after_timestamp:
                    print(f"   (filtered: only news after {after_timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
                return raw_items

            else:
                print(f"⚠️  Finnhub API error: {response.status_code}")
                return []

        except Exception as e:
            print(f"❌ Error fetching Finnhub general news: {e}")
            return []

    async def fetch_polygon_general_news(
        self,
        from_date: str,
        to_date: str,
        limit: int = 100
    ) -> List[RawNewsItem]:
        """
        Fetch general market news from Polygon.

        Args:
            from_date: Start datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            to_date: End datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            limit: Maximum number of articles

        Returns:
            List of RawNewsItem objects
        """
        try:
            print(f"🔍 Fetching Polygon general news ({from_date} to {to_date})...")

            response = await self.polygon_client.get(
                "https://api.polygon.io/v2/reference/news",
                params={
                    "published_utc.gt": from_date,  # gt = greater than (not gte to avoid duplicates)
                    "published_utc.lte": to_date,
                    "order": "desc",
                    "limit": limit,
                    "apiKey": self.polygon_api_key
                }
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                raw_items = []
                for article in results:
                    try:
                        # Fix URL field name for Polygon API
                        article['url'] = article.get('article_url', '')

                        # Use factory method to create RawNewsItem (extracts published_at)
                        raw_item = RawNewsItem.from_polygon_response(
                            symbol="GENERAL",
                            article_data=article
                        )
                        raw_items.append(raw_item)
                    except Exception as e:
                        print(f"⚠️  Error converting article: {e}")
                        continue

                print(f"✅ Fetched {len(raw_items)} general news from Polygon")
                return raw_items

            else:
                print(f"⚠️  Polygon API error: {response.status_code}")
                return []

        except Exception as e:
            print(f"❌ Error fetching Polygon general news: {e}")
            return []

    async def fetch_all_general_news(
        self,
        from_date: str,
        to_date: str
    ) -> List[RawNewsItem]:
        """
        Fetch general news from all sources.

        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            Combined list of RawNewsItem objects
        """
        print(f"📰 Fetching general news from {from_date} to {to_date}")
        print()

        # Fetch from both sources
        finnhub_items = await self.fetch_finnhub_general_news()
        polygon_items = await self.fetch_polygon_general_news(from_date, to_date, limit=100)

        all_items = finnhub_items + polygon_items

        print()
        print(f"📊 Total general news fetched: {len(all_items)}")
        print(f"   - Finnhub: {len(finnhub_items)}")
        print(f"   - Polygon: {len(polygon_items)}")

        return all_items

    async def close(self):
        """Close HTTP clients."""
        await self.finnhub_client.aclose()
        await self.polygon_client.aclose()
