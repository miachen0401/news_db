"""Database operations for stock_process_v1 table."""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class StockProcessDB:
    """Handle all database operations for stock_process_v1 table."""

    def __init__(self, supabase_client):
        """Initialize with Supabase client."""
        self.supabase = supabase_client

    async def fetch_raw_news(
        self,
        mode: str = "test",
        limit: int = 100,
        after_date: str = "2024-12-20"
    ) -> List[Dict]:
        """
        Fetch raw news from stock_news_raw table.

        Args:
            mode: "test" for last N least recent news, "production" for all after date
            limit: Number of news to fetch in test mode
            after_date: Date threshold for production mode (YYYY-MM-DD)

        Returns:
            List of raw news dictionaries
        """
        logger.info(f"Fetching raw news (mode: {mode})...")

        def _fetch():
            query = self.supabase.table("stock_news_raw").select("*")

            if mode == "test":
                # Get last N least recent news (oldest first)
                query = query.order("published_at", desc=False).limit(limit)
            else:
                # Get all news after date
                after_dt = datetime.strptime(after_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                after_iso = after_dt.isoformat()
                query = query.gte("published_at", after_iso).order("published_at", desc=False)

            return query.execute()

        result = await asyncio.to_thread(_fetch)

        if not result.data:
            logger.info("No raw news found")
            return []

        logger.info(f"Fetched {len(result.data)} raw news articles")
        return result.data

    async def fetch_unclassified_news(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch news from stock_process_v1 that haven't been classified yet.

        Args:
            limit: Optional limit on number of records to fetch

        Returns:
            List of unclassified news records
        """
        logger.info("Fetching unclassified news from stock_process_v1...")

        def _fetch():
            query = self.supabase.table("stock_process_v1").select("*").is_("event_based", "null")

            if limit:
                query = query.limit(limit)

            return query.execute()

        result = await asyncio.to_thread(_fetch)

        if not result.data:
            logger.info("No unclassified news found")
            return []

        logger.info(f"Fetched {len(result.data)} unclassified news records")
        return result.data

    async def check_existing(self, content_hash: str) -> bool:
        """
        Check if a news item with this content_hash already exists in stock_process_v1.

        Args:
            content_hash: MD5 hash of the news URL

        Returns:
            True if exists, False otherwise
        """
        def _query():
            try:
                result = self.supabase.table("stock_process_v1").select("id").eq("content_hash", content_hash).limit(1).execute()
                return len(result.data) > 0
            except Exception as e:
                logger.debug(f"Error checking existing record: {e}")
                # On connection error, assume doesn't exist to avoid blocking processing
                return False

        return await asyncio.to_thread(_query)

    async def insert_extracted_news(self, record: Dict) -> bool:
        """
        Insert extracted news data into stock_process_v1 (without classification).

        Args:
            record: Dictionary with news data (without event_based field)

        Returns:
            True if successful, False otherwise
        """
        def _insert():
            return self.supabase.table("stock_process_v1").insert(record).execute()

        try:
            await asyncio.to_thread(_insert)
            return True
        except Exception as e:
            logger.warning(f"Failed to insert news: {e}")
            return False

    async def update_classification(
        self,
        record_id: str,
        event_based: bool,
        reasoning: str,
        model_used: str,
        processing_time_ms: int
    ) -> bool:
        """
        Update a record with LLM classification results.

        Args:
            record_id: UUID of the record to update
            event_based: Boolean classification result
            reasoning: LLM reasoning from <think> tag
            model_used: Name of the LLM model
            processing_time_ms: Processing time in milliseconds

        Returns:
            True if successful, False otherwise
        """
        def _update():
            return self.supabase.table("stock_process_v1").update({
                "event_based": event_based,
                "llm_reasoning": reasoning,
                "model_used": model_used,
                "processing_time_ms": processing_time_ms,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", record_id).execute()

        try:
            await asyncio.to_thread(_update)
            return True
        except Exception as e:
            logger.warning(f"Failed to update classification for {record_id}: {e}")
            return False

    async def batch_update_classifications(
        self,
        updates: List[Dict]
    ) -> int:
        """
        Update multiple records with classification results.

        Args:
            updates: List of dicts with {id, event_based, llm_reasoning, model_used, processing_time_ms}

        Returns:
            Number of successful updates
        """
        success_count = 0

        for update in updates:
            success = await self.update_classification(
                record_id=update["id"],
                event_based=update["event_based"],
                reasoning=update["llm_reasoning"],
                model_used=update["model_used"],
                processing_time_ms=update["processing_time_ms"]
            )
            if success:
                success_count += 1

        return success_count
