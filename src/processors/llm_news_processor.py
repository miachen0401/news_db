"""LLM-based news processor with categorization."""
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.models.raw_news import RawNewsItem, ProcessingStatus
from src.storage.raw_news_storage import RawNewsStorage
from src.db.stock_news import StockNewsDB
from src.services.llm_categorizer import NewsCategorizer
from src.config import LLM_CONFIG
import logging
logger = logging.getLogger(__name__)



class LLMNewsProcessor:
    """Processor that uses LLM for categorization (no LIFO stack)."""

    def __init__(
        self,
        stock_news_db: StockNewsDB,
        raw_storage: RawNewsStorage,
        categorizer: NewsCategorizer
    ):
        """
        Initialize LLM-based processor.

        Args:
            stock_news_db: StockNewsDB instance
            raw_storage: RawNewsStorage for updating processing status
            categorizer: NewsCategorizer for LLM categorization
        """
        self.stock_news_db = stock_news_db
        self.raw_storage = raw_storage
        self.categorizer = categorizer

    def _extract_content(self, raw_item: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Extract title and summary from raw item.

        Args:
            raw_item: Raw news item from database

        Returns:
            Dict with title and summary, or None if extraction failed
        """
        raw_json = raw_item.get("raw_json")
        fetch_source = raw_item.get("fetch_source")

        if not raw_json:
            return None

        try:
            if fetch_source and fetch_source.startswith("finnhub"):
                title = raw_json.get("headline", "")
                summary = raw_json.get("summary", "")
            elif fetch_source == "polygon":
                title = raw_json.get("title", "")
                summary = raw_json.get("description", "")
            else:
                return None

            if not title:
                return None

            return {
                "title": title,
                "summary": summary or title  # Use title if no summary
            }

        except Exception as e:
            logger.debug(f"❌ Error extracting content: {e}")
            return None

    def _build_processed_data(
        self,
        raw_item: Dict[str, Any],
        categorization: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Build processed news data with categorization.

        Args:
            raw_item: Raw news item
            categorization: LLM categorization result

        Returns:
            Processed news data dict or None
        """
        try:
            raw_json = raw_item.get("raw_json", {})
            fetch_source = raw_item.get("fetch_source")
            url = raw_item.get("url", "")

            # Extract fields based on source
            if fetch_source and fetch_source.startswith("finnhub"):
                title = raw_json.get("headline", "")
                summary = raw_json.get("summary", "")
                source_name = raw_json.get("source", "")
                timestamp = raw_json.get("datetime", 0)
                published_at = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
                external_id = str(raw_json.get("id", ""))

            elif fetch_source == "polygon":
                title = raw_json.get("title", "")
                summary = raw_json.get("description", "")
                source_name = raw_json.get("publisher", "")
                published_utc = raw_json.get("published_utc", "")

                if published_utc:
                    try:
                        published_at = datetime.fromisoformat(published_utc.replace('Z', '+00:00'))
                    except:
                        published_at = datetime.now()
                else:
                    published_at = datetime.now()

                external_id = raw_json.get("id", "")

            else:
                return None

            # Build processed data
            processed_data = {
                "title": title,
                "summary": summary[:500],
                "url": url,
                "source": source_name,
                "fetch_source": fetch_source,
                "published_at": published_at.isoformat(),
                "source_id": None,
                "external_id": external_id,
                "category": categorization.get("primary_category", "UNCATEGORIZED"),
                "secondary_category": categorization.get("secondary_category", ""),
                "metadata": {
                    **raw_json,
                    "llm_confidence": categorization.get("confidence", 0.0),
                    "fetch_source": fetch_source,
                }
            }

            return processed_data

        except Exception as e:
            logger.debug(f"❌ Error building processed data: {e}")
            return None

    async def process_raw_item(
        self,
        raw_item: Dict[str, Any],
        categorization: Dict[str, Any]
    ) -> bool:
        """
        Process a single raw news item with categorization.

        Args:
            raw_item: Raw news item from database
            categorization: LLM categorization result

        Returns:
            True if processing and storage successful
        """
        item_id = raw_item.get("id")

        if not item_id:
            return False

        # Update status to processing
        await self.raw_storage.update_processing_status(
            item_id,
            ProcessingStatus.PROCESSING
        )

        try:
            # Build processed data
            processed_data = self._build_processed_data(raw_item, categorization)

            if not processed_data:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.FAILED,
                    error_log="Failed to build processed data"
                )
                return False

            # Filter out NON_FINANCIAL news
            if processed_data.get("category") == "NON_FINANCIAL":
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.COMPLETED
                )
                logger.debug(f"⏭️  Skipped NON_FINANCIAL: {processed_data['title'][:50]}...")
                return True  # Mark as successful but don't store

            # Handle ERROR category - store with error_log
            if processed_data.get("category") == "ERROR":
                error_log = categorization.get("api_error", "Unknown error")
                # Store ERROR items so they can be manually reviewed
                processed_data["metadata"]["error_log"] = error_log
                logger.debug(f"⚠️  ERROR category: {processed_data['title'][:50]}... - {error_log[:50]}")
            # Store in stock_news table (no LIFO stack, just insert)
            result = await self.stock_news_db.insert_news(processed_data)

            if result:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.COMPLETED
                )
                cat = processed_data.get('category', '')
                sec_cat = processed_data.get('secondary_category', '')
                logger.debug(f"✅ Stored [{cat}] {processed_data['title'][:45]}... ({sec_cat or 'general'})")
                return True
            else:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.FAILED,
                    error_log="Failed to insert into stock_news"
                )
                return False

        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            await self.raw_storage.update_processing_status(
                item_id,
                ProcessingStatus.FAILED,
                error_log=error_msg
            )
            logger.debug(f"❌ {error_msg}")
            return False

    async def process_unprocessed_batch(self, limit: int = 50) -> Dict[str, int]:
        """
        Process a batch of unprocessed raw news with LLM categorization.

        Args:
            limit: Maximum number of items to process

        Returns:
            Statistics dict with counts
        """
        stats = {
            "fetched": 0,
            "categorized": 0,
            "processed": 0,
            "non_financial_skipped": 0,
            "failed": 0
        }

        # Get unprocessed items
        unprocessed = await self.raw_storage.get_unprocessed(limit=limit)
        stats["fetched"] = len(unprocessed)

        if not unprocessed:
            return stats

        logger.debug(f"📊 Processing {stats['fetched']} unprocessed news items...")
        # Extract titles and summaries for LLM
        news_for_llm = []
        for item in unprocessed:
            content = self._extract_content(item)
            if content:
                news_for_llm.append({
                    **content,
                    "raw_item": item
                })

        # Categorize with LLM in batch
        if news_for_llm:
            logger.debug(f"🤖 Sending {len(news_for_llm)} items to LLM for categorization...")
            categorized = await self.categorizer.categorize_batch(
                news_for_llm,
                batch_size=LLM_CONFIG['batch_size']
            )
            stats["categorized"] = len(categorized)

            # Process each categorized item
            for item_data in categorized:
                raw_item = item_data.get("raw_item")
                if not raw_item:
                    continue

                success = await self.process_raw_item(raw_item, item_data)

                if success:
                    if item_data.get("primary_category") == "NON_FINANCIAL":
                        stats["non_financial_skipped"] += 1
                    else:
                        stats["processed"] += 1
                else:
                    stats["failed"] += 1

        logger.debug(f"✅ Processing complete:")
        logger.debug(f"   Categorized: {stats['categorized']}")
        logger.debug(f"   Stored: {stats['processed']}")
        logger.debug(f"   NON_FINANCIAL skipped: {stats['non_financial_skipped']}")
        logger.debug(f"   Failed: {stats['failed']}")
        return stats

    async def recategorize_uncategorized_batch(self, limit: int = 50) -> Dict[str, int]:
        """
        Re-process UNCATEGORIZED news items in stock_news table.

        Args:
            limit: Maximum number of items to re-process

        Returns:
            Statistics dict with counts
        """
        stats = {
            "fetched": 0,
            "recategorized": 0,
            "updated": 0,
            "non_financial_removed": 0,
            "failed": 0
        }

        # Get UNCATEGORIZED items from stock_news
        uncategorized = await self.stock_news_db.get_uncategorized(limit=limit)
        stats["fetched"] = len(uncategorized)

        if not uncategorized:
            return stats

        logger.debug(f"🔄 Re-processing {stats['fetched']} UNCATEGORIZED news items...")
        # Extract titles and summaries for LLM
        news_for_llm = []
        for item in uncategorized:
            title = item.get("title", "")
            summary = item.get("summary", "")
            if title:
                news_for_llm.append({
                    "title": title,
                    "summary": summary or title,
                    "stock_news_item": item
                })

        # Categorize with LLM in batch
        if news_for_llm:
            logger.debug(f"🤖 Sending {len(news_for_llm)} items to LLM for re-categorization...")
            categorized = await self.categorizer.categorize_batch(
                news_for_llm,
                batch_size=LLM_CONFIG['batch_size']
            )
            stats["recategorized"] = len(categorized)

            # Update each item with new category
            for item_data in categorized:
                stock_item = item_data.get("stock_news_item")
                if not stock_item:
                    continue

                item_id = stock_item.get("id")
                new_category = item_data.get("primary_category", "UNCATEGORIZED")
                new_secondary = item_data.get("secondary_category", "")
                api_error = item_data.get("api_error", None)

                # If ERROR category, save error_log and don't retry again
                if new_category == "ERROR":
                    error_log = api_error or "Unknown error during re-categorization"
                    success = await self.stock_news_db.update_category(
                        item_id=item_id,
                        category="ERROR",
                        secondary_category="",
                        error_log=error_log
                    )
                    if success:
                        stats["failed"] += 1
                        logger.debug(f"❌ ERROR (will not retry): {stock_item.get('title', '')[:40]}... - {error_log[:50]}")
                    continue

                # If still UNCATEGORIZED after retry, skip (will retry next time)
                if new_category == "UNCATEGORIZED":
                    stats["failed"] += 1
                    logger.debug(f"⚠️  Still UNCATEGORIZED: {stock_item.get('title', '')[:50]}...")
                    continue

                # If NON_FINANCIAL, update category
                if new_category == "NON_FINANCIAL":
                    stats["non_financial_removed"] += 1
                    logger.debug(f"🗑️  Marked as NON_FINANCIAL: {stock_item.get('title', '')[:50]}...")
                # Update category (clear error_log if previously had error)
                success = await self.stock_news_db.update_category(
                    item_id=item_id,
                    category=new_category,
                    secondary_category=new_secondary,
                    error_log=""  # Clear any previous error
                )

                if success:
                    stats["updated"] += 1
                    logger.debug(f"✅ Updated [{new_category}] {stock_item.get('title', '')[:45]}... ({new_secondary or 'general'})")
                else:
                    stats["failed"] += 1

        logger.debug(f"✅ Re-categorization complete:")
        logger.debug(f"   Re-categorized: {stats['recategorized']}")
        logger.debug(f"   Updated: {stats['updated']}")
        logger.debug(f"   NON_FINANCIAL marked: {stats['non_financial_removed']}")
        logger.debug(f"   Failed: {stats['failed']}")
        return stats
