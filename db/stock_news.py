"""Database operations for stock_news table."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from supabase import Client
import asyncio


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
                    print(f"⚠️  Duplicate URL detected, skipping: {url[:50]}...")
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

            return None

        except Exception as e:
            print(f"❌ Error inserting news: {e}")
            return None

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
            print(f"❌ Error getting stats: {e}")
            return {"total": 0}
