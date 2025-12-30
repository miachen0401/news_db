"""Duplicate checking and filtering utilities for news processing."""
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class DuplicateFilter:
    """
    Handles duplicate checking and filtering across raw and processed news.

    Used by both fetch and recategorization services to maintain data consistency.
    """

    def __init__(self, stock_news_db, raw_storage):
        """
        Initialize duplicate filter.

        Args:
            stock_news_db: StockNewsDB instance
            raw_storage: RawNewsStorage instance
        """
        self.stock_news_db = stock_news_db
        self.raw_storage = raw_storage

    async def filter_and_mark_duplicates(
        self,
        items: List[Dict[str, Any]],
        processing_status,
        item_type: str = "items"
    ) -> int:
        """
        Check items for duplicates in stock_news table and mark them as completed.

        Args:
            items: List of raw news items to check
            processing_status: ProcessingStatus enum (for marking as COMPLETED)
            item_type: Description of item type for logging (e.g., "failed items", "pending items")

        Returns:
            Number of duplicates found and marked as completed
        """
        if not items:
            return 0

        logger.info(f"Checking {len(items)} {item_type} for duplicates in stock_news...")

        duplicate_count = 0
        for item in items:
            url = item.get("url")
            if url and await self.stock_news_db.check_url_exists(url):
                # Mark as completed with "Duplicate URL" error_log
                await self.raw_storage.update_processing_status(
                    item["id"],
                    processing_status.COMPLETED,
                    error_log="Duplicate URL - already exists in stock_news"
                )
                duplicate_count += 1

        if duplicate_count > 0:
            logger.info(f"Marked {duplicate_count} duplicate {item_type} as completed")

        return duplicate_count
