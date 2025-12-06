"""General news fetcher without symbol filtering."""
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import httpx

from src.models.raw_news import RawNewsItem
import logging
logger = logging.getLogger(__name__)



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
        categories: List[str] = None,
        min_id: int = 0
    ) -> Tuple[List[RawNewsItem], int]:
        """
        Fetch general market news from Finnhub across multiple categories.

        Note: Finnhub API returns latest ~100 articles per category.
        Uses minId parameter for incremental fetching (fetches news with ID > minId).

        Args:
            categories: List of news categories to fetch (general, forex, crypto, merger)
            min_id: Minimum news ID for incremental fetching (fetch news with ID > minId)

        Returns:
            Tuple of (List of RawNewsItem objects, max_id seen)
        """
        if categories is None:
            categories = ["general"]

        all_raw_items = []
        max_id_seen = min_id

        for category in categories:
            try:
                logger.debug(f"Fetching Finnhub '{category}' news (minId={min_id})...")
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
                            # Track max ID for next incremental fetch
                            article_id = article.get('id', 0)
                            if article_id > max_id_seen:
                                max_id_seen = article_id

                            # Use factory method to create RawNewsItem (extracts published_at)
                            raw_item = RawNewsItem.from_finnhub_response(
                                symbol="GENERAL",
                                article_data=article,
                                category=category
                            )

                            raw_items.append(raw_item)
                        except Exception as e:
                            logger.debug(f"Error converting article: {e}")
                            continue

                    logger.debug(f"Fetched {len(raw_items)} news from Finnhub '{category}'")
                    all_raw_items.extend(raw_items)

                else:
                    logger.debug(f"Finnhub '{category}' API error: {response.status_code}")
            except Exception as e:
                logger.debug(f"Error fetching Finnhub '{category}' news: {e}")
        logger.debug(f"Total Finnhub news: {len(all_raw_items)} (max_id: {max_id_seen})")
        return all_raw_items, max_id_seen

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
            logger.debug(f"Fetching Polygon general news ({from_date} to {to_date})...")
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
                        logger.debug(f"Error converting article: {e}")
                        continue

                logger.debug(f"Fetched {len(raw_items)} general news from Polygon")
                return raw_items

            else:
                logger.debug(f"Polygon API error: {response.status_code}")
                return []

        except Exception as e:
            logger.debug(f"Error fetching Polygon general news: {e}")
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
        logger.debug(f"📰 Fetching general news from {from_date} to {to_date}")
        logger.debug("")
        # Fetch from both sources
        finnhub_items = await self.fetch_finnhub_general_news()
        polygon_items = await self.fetch_polygon_general_news(from_date, to_date, limit=100)

        all_items = finnhub_items + polygon_items

        logger.debug("")
        logger.debug(f"📊 Total general news fetched: {len(all_items)}")
        logger.debug(f"   - Finnhub: {len(finnhub_items)}")
        logger.debug(f"   - Polygon: {len(polygon_items)}")
        return all_items

    async def fetch_company_news(
        self,
        symbol: str,
        from_timestamp: datetime,
        to_timestamp: datetime
    ) -> List[RawNewsItem]:
        """
        Fetch company-specific news from Finnhub /company-news API.

        Args:
            symbol: Stock ticker symbol (e.g., AAPL, TSLA)
            from_timestamp: Start datetime (UTC)
            to_timestamp: End datetime (UTC)

        Returns:
            List of RawNewsItem objects
        """
        try:
            # Convert datetime to YYYY-MM-DD format for Finnhub API
            from_date = from_timestamp.strftime("%Y-%m-%d")
            to_date = to_timestamp.strftime("%Y-%m-%d")

            logger.debug(f"Fetching Finnhub company news for {symbol} ({from_date} to {to_date})...")
            response = await self.finnhub_client.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": symbol,
                    "from": from_date,
                    "to": to_date,
                    "token": self.finnhub_api_key
                }
            )

            if response.status_code == 200:
                articles = response.json()

                # Filter by timestamp (API returns date-based results, need to filter by exact time)
                raw_items = []
                for article in articles:
                    try:
                        # Use factory method to create RawNewsItem (extracts published_at)
                        raw_item = RawNewsItem.from_finnhub_response(
                            symbol=symbol,
                            article_data=article,
                            category=f"company_{symbol}"
                        )

                        # Filter by timestamp (only news after from_timestamp)
                        if raw_item.published_at and raw_item.published_at > from_timestamp:
                            raw_items.append(raw_item)

                    except Exception as e:
                        logger.debug(f"Error converting article: {e}")
                        continue

                logger.debug(f"Fetched {len(raw_items)} news for {symbol}")
                return raw_items

            else:
                logger.debug(f"Finnhub company-news API error for {symbol}: {response.status_code}")
                return []

        except Exception as e:
            logger.debug(f"Error fetching company news for {symbol}: {e}")
            return []

    async def close(self):
        """Close HTTP clients."""
        await self.finnhub_client.aclose()
        await self.polygon_client.aclose()
