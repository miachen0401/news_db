"""LLM-based news processor with categorization."""
from typing import Dict, Any, Optional, List
from datetime import datetime

from models.raw_news import RawNewsItem, ProcessingStatus
from storage.raw_news_storage import RawNewsStorage
from db.stock_news import StockNewsDB
from services.llm_categorizer import NewsCategorizer


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
            if fetch_source == "finnhub":
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
            print(f"❌ Error extracting content: {e}")
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
            if fetch_source == "finnhub":
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
            print(f"❌ Error building processed data: {e}")
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
                print(f"⏭️  Skipped NON_FINANCIAL: {processed_data['title'][:50]}...")
                return True  # Mark as successful but don't store

            # Store in stock_news table (no LIFO stack, just insert)
            result = await self.stock_news_db.insert_news(processed_data)

            if result:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.COMPLETED
                )
                cat = processed_data.get('category', '')
                sec_cat = processed_data.get('secondary_category', '')
                print(f"✅ Stored [{cat}] {processed_data['title'][:45]}... ({sec_cat or 'general'})")
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
            print(f"❌ {error_msg}")
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

        print(f"📊 Processing {stats['fetched']} unprocessed news items...")

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
            print(f"🤖 Sending {len(news_for_llm)} items to LLM for categorization...")

            categorized = await self.categorizer.categorize_batch(news_for_llm)
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

        print(f"✅ Processing complete:")
        print(f"   Categorized: {stats['categorized']}")
        print(f"   Stored: {stats['processed']}")
        print(f"   NON_FINANCIAL skipped: {stats['non_financial_skipped']}")
        print(f"   Failed: {stats['failed']}")

        return stats
