"""LLM-based news processor with categorization."""
from typing import Dict, Any, Optional
from datetime import datetime

from src.models.raw_news import ProcessingStatus
from src.storage.raw_news_storage import RawNewsStorage
from src.db.stock_news import StockNewsDB
from src.services.llm_categorizer import NewsCategorizer
from src.config import LLM_CONFIG, EXCLUDED_CATEGORIES
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
            logger.debug(f"Error extracting content: {e}")
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
                "symbol": categorization.get("symbol", ""),
                "metadata": {
                    **raw_json,
                    "llm_confidence": categorization.get("confidence", 0.0),
                    "fetch_source": fetch_source,
                }
            }

            return processed_data

        except Exception as e:
            logger.debug(f"Error building processed data: {e}")
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

            # Filter out excluded categories (NON_FINANCIAL, MACRO_NOBODY, etc.)
            if processed_data.get("category") in EXCLUDED_CATEGORIES:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.COMPLETED
                )
                category = processed_data.get("category")
                logger.debug(f"Skipped {category}: {processed_data['title'][:50]}...")
                return True  # Mark as successful but don't store

            # Handle ERROR category - store with error_log
            if processed_data.get("category") == "ERROR":
                error_log = categorization.get("api_error", "Unknown error")
                # Store ERROR items so they can be manually reviewed
                processed_data["metadata"]["error_log"] = error_log
                logger.debug(f"ERROR category: {processed_data['title'][:50]}... - {error_log[:50]}")
            # Store in stock_news table (no LIFO stack, just insert)
            result, error_msg = await self.stock_news_db.insert_news(processed_data)

            if result:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.COMPLETED
                )
                cat = processed_data.get('category', '')
                symbol = processed_data.get('symbol', '')
                logger.debug(f"Stored [{cat}] {processed_data['title'][:45]}... ({symbol or 'GENERAL'})")
                return True
            else:
                # Use the detailed error message from insert_news
                if not error_msg:
                    error_msg = f"Failed to insert into stock_news (URL: {processed_data.get('url', '')[:50]})"
                logger.warning(f"Insert failed for item {item_id}: {processed_data.get('title', '')[:50]} - {error_msg}")
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.FAILED,
                    error_log=error_msg
                )
                return False

        except Exception as e:
            error_msg = f"Processing error: {str(e)}"
            await self.raw_storage.update_processing_status(
                item_id,
                ProcessingStatus.FAILED,
                error_log=error_msg
            )
            logger.debug(f"{error_msg}")
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
            "excluded_skipped": 0,
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
            logger.info(f"Sending {len(news_for_llm)} items to LLM for categorization...")
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
                    if item_data.get("primary_category") in EXCLUDED_CATEGORIES:
                        stats["excluded_skipped"] += 1
                    else:
                        stats["processed"] += 1
                else:
                    stats["failed"] += 1

        logger.info(f"Processing complete:")
        logger.info(f"   Categorized: {stats['categorized']}")
        logger.info(f"   Stored: {stats['processed']}")
        logger.info(f"   Excluded skipped: {stats['excluded_skipped']}")
        logger.info(f"   Failed: {stats['failed']}")
        return stats

    async def prefilter_nobody_categories(self) -> int:
        """
        Pre-filter items with "nobody" in category name.

        Categories containing "nobody" are too generic/non-specific.
        Mark them as MACRO_NOBODY directly without LLM calls.

        Returns:
            Number of items filtered
        """
        # Get ALL items needing re-categorization
        all_items = await self.stock_news_db.get_items_needing_recategorization(limit=1000)

        if not all_items:
            return 0

        nobody_filtered = 0

        for item in all_items:
            category = item.get("category", "")
            item_id = item.get("id")

            # Check if category contains "nobody" (case-insensitive)
            if "nobody" in category.lower():
                # Mark as MACRO_NOBODY directly
                success = await self.stock_news_db.update_category(
                    item_id=item_id,
                    category="MACRO_NOBODY",
                    symbol="",
                    error_log=f"Auto-filtered: category contained 'nobody' ({category})"
                )
                if success:
                    nobody_filtered += 1
                    logger.debug(f"Filtered [{category}→MACRO_NOBODY] {item.get('title', '')[:50]}...")

        return nobody_filtered

    async def normalize_space_categories(self) -> int:
        """
        Normalize categories with spaces to underscores.

        Fixes categories like "CORPORATE ACTION" → "CORPORATE_ACTION".

        Returns:
            Number of items normalized
        """
        # Import the normalize function
        from src.services.llm_categorizer import normalize_category

        # Get ALL items needing re-categorization
        all_items = await self.stock_news_db.get_items_needing_recategorization(limit=1000)

        if not all_items:
            return 0

        normalized_count = 0

        for item in all_items:
            category = item.get("category", "")
            item_id = item.get("id")

            # Check if category contains spaces or needs normalization
            if ' ' in category or '-' in category:
                normalized_category = normalize_category(category)

                # Only update if the normalized version is different
                if normalized_category != category:
                    success = await self.stock_news_db.update_category(
                        item_id=item_id,
                        category=normalized_category,
                        symbol=item.get("symbol", ""),
                        error_log=f"Auto-normalized: '{category}' → '{normalized_category}'"
                    )
                    if success:
                        normalized_count += 1
                        logger.debug(f"Normalized [{category}→{normalized_category}] {item.get('title', '')[:50]}...")

        return normalized_count

    async def recategorize_batch(self, limit: int = 50, items_to_fix: list = None) -> Dict[str, int]:
        """
        Re-process items needing re-categorization (UNCATEGORIZED + invalid categories).

        This unified method handles all items with problematic categories:
        - UNCATEGORIZED: Failed initial categorization
        - Invalid categories: Not in ALLOWED_CATEGORIES (LLM hallucinations, typos, old schema)

        Excludes:
        - ERROR: Permanent failures (don't retry)
        - All valid categories from ALLOWED_CATEGORIES

        Args:
            limit: Maximum number of items to re-process (only used if items_to_fix is None)
            items_to_fix: Optional list of items to process. If provided, processes these specific items.
                         If None, queries database for items needing re-categorization.

        Returns:
            Statistics dict with counts
        """
        stats = {
            "fetched": 0,
            "recategorized": 0,
            "updated": 0,
            "excluded_marked": 0,
            "failed": 0
        }

        # Get items to fix (either from parameter or query database)
        if items_to_fix is None:
            items_to_fix = await self.stock_news_db.get_items_needing_recategorization(limit=limit)

        stats["fetched"] = len(items_to_fix)

        if not items_to_fix:
            return stats

        logger.debug(f"🔄 Re-processing {stats['fetched']} items needing re-categorization...")

        # Log the categories found (for audit trail)
        category_breakdown = {}
        for item in items_to_fix:
            cat = item.get("category", "UNKNOWN")
            category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

        logger.info(f"Categories needing fixes:")
        for cat, count in sorted(category_breakdown.items(), key=lambda x: -x[1]):
            logger.info(f"   {cat}: {count}")

        logger.debug("")

        # Extract titles and summaries for LLM
        news_for_llm = []
        for item in items_to_fix:
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
            logger.info(f"Sending {len(news_for_llm)} items to LLM for re-categorization...")
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
                old_category = stock_item.get("category", "UNKNOWN")
                new_category = item_data.get("primary_category", "UNCATEGORIZED")
                new_symbol = item_data.get("symbol", "")
                api_error = item_data.get("api_error", None)

                # If ERROR category, save error_log and don't retry again
                if new_category == "ERROR":
                    error_log = api_error or "Unknown error during re-categorization"
                    success = await self.stock_news_db.update_category(
                        item_id=item_id,
                        category="ERROR",
                        symbol="",
                        error_log=error_log
                    )
                    if success:
                        stats["failed"] += 1
                        logger.debug(f"ERROR (will not retry): {stock_item.get('title', '')[:40]}... - {error_log[:50]}")
                    continue

                # If still UNCATEGORIZED after retry, mark it
                if new_category == "UNCATEGORIZED":
                    success = await self.stock_news_db.update_category(
                        item_id=item_id,
                        category="UNCATEGORIZED",
                        symbol="",
                        error_log=f"Changed from invalid category: {old_category}"
                    )
                    if success:
                        stats["failed"] += 1
                        logger.debug(f"Changed to UNCATEGORIZED (was {old_category}): {stock_item.get('title', '')[:50]}...")
                    continue

                # If excluded category, count it
                if new_category in EXCLUDED_CATEGORIES:
                    stats["excluded_marked"] += 1
                    logger.debug(f"Marked as {new_category} (was {old_category}): {stock_item.get('title', '')[:50]}...")

                # Update category (clear error_log if previously had error)
                success = await self.stock_news_db.update_category(
                    item_id=item_id,
                    category=new_category,
                    symbol=new_symbol,
                    error_log=""  # Clear any previous error
                )

                if success:
                    stats["updated"] += 1
                    if old_category != new_category:
                        logger.debug(f"Fixed [{old_category}→{new_category}] {stock_item.get('title', '')[:45]}... ({new_symbol or 'GENERAL'})")
                    else:
                        logger.debug(f"Updated [{new_category}] {stock_item.get('title', '')[:45]}... ({new_symbol or 'GENERAL'})")
                else:
                    stats["failed"] += 1

        logger.info(f"Re-categorization complete:")
        logger.info(f"   Re-categorized: {stats['recategorized']}")
        logger.info(f"   Updated: {stats['updated']}")
        logger.info(f"   Excluded marked: {stats['excluded_marked']}")
        logger.info(f"   Failed: {stats['failed']}")
        return stats
