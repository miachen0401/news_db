"""Database operations for stock_news table."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from supabase import Client
import asyncio
import logging

from src.config import ALLOWED_CATEGORIES

logger = logging.getLogger(__name__)



class StockNewsDB:
    """Database operations for stock_news table."""

    def __init__(self, client: Client):
        """
        Initialize with Supabase client.

        Args:
            client: Supabase client instance
        """
        self.client = client
        self.table_name = "stock_news"

    async def insert_news(
        self,
        news_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Insert news directly (no LIFO stack).

        Args:
            news_data: News data to insert

        Returns:
            Inserted news item or None if failed
        """
        try:
            url = news_data.get("url")

            # Check for duplicate URL globally
            if url:
                def _check_dup():
                    return (
                        self.client
                        .table(self.table_name)
                        .select("id")
                        .eq("url", url)
                        .limit(1)
                        .execute()
                    )

                dup_result = await asyncio.to_thread(_check_dup)
                if dup_result.data:
                    logger.debug(f"Duplicate URL detected, skipping: {url[:50]}...")
                    return None

            # Prepare news item (no position_in_stack)
            news_item = {
                "symbol": news_data.get("secondary_category", "GENERAL"),  # Use secondary_category as symbol
                "title": news_data.get("title", ""),
                "summary": news_data.get("summary", ""),
                "url": url,
                "source": news_data.get("source"),
                "fetch_source": news_data.get("fetch_source"),
                "published_at": news_data.get("published_at"),
                "category": news_data.get("category"),
                "secondary_category": news_data.get("secondary_category", ""),
                "source_id": news_data.get("source_id"),
                "external_id": news_data.get("external_id"),
                "metadata": news_data.get("metadata", {}),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            # Insert into database
            def _insert():
                return self.client.table(self.table_name).insert(news_item).execute()

            result = await asyncio.to_thread(_insert)

            if result.data:
                return result.data[0]
            else:
                logger.error(f"Insert failed but no exception: {url[:50] if url else 'no url'}")
                return None

        except Exception as e:
            logger.error(f"Error inserting news into stock_news: {type(e).__name__}: {str(e)}")
            logger.error(f"  URL: {url[:80] if url else 'no url'}")
            logger.error(f"  Category: {news_data.get('category')}")
            return None

    async def count_items_needing_recategorization(self) -> int:
        """
        Count items that need re-categorization.

        Items needing re-categorization include:
        - UNCATEGORIZED: Failed initial categorization
        - Invalid categories: Not in ALLOWED_CATEGORIES list (LLM hallucinations, typos)

        Excludes:
        - ERROR: Permanent failures (don't retry)
        - All valid categories in ALLOWED_CATEGORIES (including those not used in daily summary)

        Returns:
            Number of items needing re-categorization
        """
        # Valid categories that DON'T need re-categorization
        # = ALLOWED_CATEGORIES (all valid categories) + ERROR (permanent failures)
        CATEGORIES_TO_SKIP = ALLOWED_CATEGORIES + ["ERROR"]

        try:
            def _count():
                return (
                    self.client
                    .table(self.table_name)
                    .select("id", count="exact")
                    .not_.in_("category", CATEGORIES_TO_SKIP)
                    .execute()
                )

            result = await asyncio.to_thread(_count)
            return result.count or 0

        except Exception as e:
            logger.debug(f"Error counting items needing recategorization: {e}")
            return 0

    async def get_items_needing_recategorization(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get items that need re-categorization.

        This unified method replaces separate get_uncategorized() and get_invalid_categories()
        by querying all items with categories not in the valid list.

        Items returned include:
        - UNCATEGORIZED: Failed initial categorization, need retry
        - Invalid categories: Categories not in ALLOWED_CATEGORIES (hallucinations, typos, old schema)

        Excludes:
        - ERROR: Permanent failures (don't retry to avoid infinite loops)
        - All valid categories from ALLOWED_CATEGORIES (including those not used in daily summary)

        Args:
            limit: Maximum number of items to fetch

        Returns:
            List of news items needing re-categorization, ordered by created_at (oldest first)
        """
        # Valid categories that DON'T need re-categorization
        CATEGORIES_TO_SKIP = ALLOWED_CATEGORIES + ["ERROR"]

        try:
            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .not_.in_("category", CATEGORIES_TO_SKIP)
                    .order("created_at", desc=False)  # Process oldest first
                    .limit(limit)
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)
            return result.data or []

        except Exception as e:
            logger.debug(f"Error getting items needing recategorization: {e}")
            return []

    async def update_category(
        self,
        item_id: str,
        category: str,
        secondary_category: str = "",
        error_log: Optional[str] = None
    ) -> bool:
        """
        Update category and secondary_category for a news item.

        Args:
            item_id: News item ID
            category: New primary category
            secondary_category: New secondary category (stock symbols)
            error_log: Error message if categorization failed

        Returns:
            True if update successful
        """
        try:
            update_data = {
                "category": category,
                "secondary_category": secondary_category,
                "updated_at": datetime.now().isoformat()
            }

            # Add error_log if provided
            if error_log is not None:
                update_data["error_log"] = error_log

            def _update():
                return (
                    self.client
                    .table(self.table_name)
                    .update(update_data)
                    .eq("id", item_id)
                    .execute()
                )

            result = await asyncio.to_thread(_update)
            return result.data is not None

        except Exception as e:
            logger.debug(f"Error updating category: {e}")
            return False


    async def get_stats(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics for stock news.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            Statistics dictionary
        """
        try:
            def _get_count():
                query = self.client.table(self.table_name).select("id", count="exact")
                if symbol:
                    query = query.eq("symbol", symbol.upper())
                return query.execute()

            result = await asyncio.to_thread(_get_count)

            stats = {
                "total": result.count or 0,
            }

            if symbol:
                stats["symbol"] = symbol.upper()

            return stats

        except Exception as e:
            logger.debug(f"Error getting stats: {e}")
            return {"total": 0}
