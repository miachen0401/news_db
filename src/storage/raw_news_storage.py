"""Database operations for stock_news_raw table."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from supabase import Client
import asyncio

from src.models.raw_news import RawNewsItem, ProcessingStatus
import logging
logger = logging.getLogger(__name__)



class RawNewsStorage:
    """Database operations for stock_news_raw table (data lake)."""

    def __init__(self, client: Client):
        """
        Initialize storage with Supabase client.

        Args:
            client: Supabase client instance
        """
        self.client = client
        self.table_name = "stock_news_raw"

    async def insert(self, item: RawNewsItem) -> Optional[Dict[str, Any]]:
        """
        Insert single raw news item into database.

        Args:
            item: RawNewsItem to insert

        Returns:
            Inserted item data or None if failed
        """
        try:
            # Check for duplicates first
            if await self.check_duplicate(item.content_hash or item.generate_content_hash()):
                logger.debug(f"⚠️  Duplicate content hash detected, skipping: {item.url}")
                return None

            # Convert to database dict
            data = item.to_db_dict()

            # Insert into database
            def _insert():
                return self.client.table(self.table_name).insert(data).execute()

            result = await asyncio.to_thread(_insert)

            if result.data:
                logger.debug(f"✅ Inserted raw news for {item.symbol}: {item.url[:50]}...")
                return result.data[0]

            return None

        except Exception as e:
            logger.debug(f"❌ Error inserting raw news: {e}")
            return None

    async def bulk_insert(self, items: List[RawNewsItem]) -> Dict[str, int]:
        """
        Insert multiple raw news items.

        Args:
            items: List of RawNewsItem objects

        Returns:
            Statistics dict with counts
        """
        stats = {"total": len(items), "inserted": 0, "duplicates": 0, "failed": 0}

        for item in items:
            result = await self.insert(item)
            if result:
                stats["inserted"] += 1
            elif await self.check_duplicate(item.content_hash or item.generate_content_hash()):
                stats["duplicates"] += 1
            else:
                stats["failed"] += 1

        logger.debug(f"📊 Bulk insert stats: {stats}")
        return stats

    async def check_duplicate(self, content_hash: str) -> bool:
        """
        Check if content hash already exists.

        Args:
            content_hash: MD5 hash of URL

        Returns:
            True if duplicate exists
        """
        try:
            def _check():
                return (
                    self.client
                    .table(self.table_name)
                    .select("id")
                    .eq("content_hash", content_hash)
                    .limit(1)
                    .execute()
                )

            result = await asyncio.to_thread(_check)
            return len(result.data) > 0

        except Exception as e:
            logger.debug(f"❌ Error checking duplicate: {e}")
            return False

    async def count_pending(self) -> int:
        """
        Count pending raw news items.

        Returns:
            Number of pending items
        """
        try:
            def _count():
                return (
                    self.client
                    .table(self.table_name)
                    .select("id", count="exact")
                    .eq("processing_status", ProcessingStatus.PENDING.value)
                    .execute()
                )

            result = await asyncio.to_thread(_count)
            return result.count or 0

        except Exception as e:
            logger.debug(f"❌ Error counting pending news: {e}")
            return 0

    async def get_unprocessed(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get unprocessed raw news items.

        Args:
            limit: Maximum number of items to fetch

        Returns:
            List of unprocessed raw news items
        """
        try:
            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .eq("is_processed", False)
                    .eq("processing_status", ProcessingStatus.PENDING.value)
                    .order("created_at", desc=False)  # Process oldest first
                    .limit(limit)
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)
            return result.data or []

        except Exception as e:
            logger.debug(f"❌ Error getting unprocessed news: {e}")
            return []

    async def get_by_symbol(
        self,
        symbol: str,
        limit: int = 50,
        include_processed: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get raw news for a specific symbol.

        Args:
            symbol: Stock ticker symbol
            limit: Maximum number of items
            include_processed: Include processed items

        Returns:
            List of raw news items
        """
        try:
            def _fetch():
                query = (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .eq("symbol", symbol.upper())
                )

                if not include_processed:
                    query = query.eq("is_processed", False)

                return query.order("fetched_at", desc=True).limit(limit).execute()

            result = await asyncio.to_thread(_fetch)
            return result.data or []

        except Exception as e:
            logger.debug(f"❌ Error getting news for {symbol}: {e}")
            return []

    async def update_processing_status(
        self,
        item_id: str,
        status: ProcessingStatus,
        error_log: Optional[str] = None
    ) -> bool:
        """
        Update processing status of a raw news item.

        Args:
            item_id: Raw news item ID
            status: New processing status
            error_log: Optional error message

        Returns:
            True if update successful
        """
        try:
            update_data: Dict[str, Any] = {
                "processing_status": status.value,
                "updated_at": datetime.now().isoformat()
            }

            if status == ProcessingStatus.COMPLETED:
                update_data["is_processed"] = True
                update_data["processed_at"] = datetime.now().isoformat()

            if error_log:
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
            logger.debug(f"❌ Error updating processing status: {e}")
            return False

    async def delete_old_processed(self, days: int = 30) -> int:
        """
        Delete processed raw news older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of deleted items
        """
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            def _delete():
                return (
                    self.client
                    .table(self.table_name)
                    .delete()
                    .eq("is_processed", True)
                    .lt("processed_at", cutoff_date)
                    .execute()
                )

            result = await asyncio.to_thread(_delete)
            deleted_count = len(result.data) if result.data else 0
            logger.debug(f"🗑️  Deleted {deleted_count} old processed items (>{days} days)")
            return deleted_count

        except Exception as e:
            logger.debug(f"❌ Error deleting old processed news: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Statistics dictionary
        """
        try:
            def _get_total():
                return self.client.table(self.table_name).select("id", count="exact").execute()

            def _get_pending():
                return (
                    self.client
                    .table(self.table_name)
                    .select("id", count="exact")
                    .eq("processing_status", ProcessingStatus.PENDING.value)
                    .execute()
                )

            def _get_completed():
                return (
                    self.client
                    .table(self.table_name)
                    .select("id", count="exact")
                    .eq("processing_status", ProcessingStatus.COMPLETED.value)
                    .execute()
                )

            def _get_failed():
                return (
                    self.client
                    .table(self.table_name)
                    .select("id", count="exact")
                    .eq("processing_status", ProcessingStatus.FAILED.value)
                    .execute()
                )

            total_result = await asyncio.to_thread(_get_total)
            pending_result = await asyncio.to_thread(_get_pending)
            completed_result = await asyncio.to_thread(_get_completed)
            failed_result = await asyncio.to_thread(_get_failed)

            stats = {
                "total": total_result.count or 0,
                "pending": pending_result.count or 0,
                "completed": completed_result.count or 0,
                "failed": failed_result.count or 0,
                "processing": 0  # Would need separate query
            }

            return stats

        except Exception as e:
            logger.debug(f"❌ Error getting stats: {e}")
            return {"total": 0, "pending": 0, "completed": 0, "failed": 0, "processing": 0}
