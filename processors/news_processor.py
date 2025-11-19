"""News processor for converting raw data to structured format."""
from typing import Dict, Any, Optional
from datetime import datetime

from models.raw_news import RawNewsItem, ProcessingStatus
from storage.raw_news_storage import RawNewsStorage
from db.stock_news import StockNewsDB


class NewsProcessor:
    """Processor for converting raw news to structured format."""

    def __init__(self, stock_news_db: 'StockNewsDB', raw_storage: RawNewsStorage):
        """
        Initialize processor.

        Args:
            stock_news_db: StockNewsDB instance for writing processed news
            raw_storage: RawNewsStorage for updating processing status
        """
        self.stock_news_db = stock_news_db
        self.raw_storage = raw_storage

    def _process_finnhub_json(self, raw_json: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """
        Process Finnhub JSON format to structured news data.

        Args:
            raw_json: Raw JSON from Finnhub API
            symbol: Stock symbol

        Returns:
            Processed news data dict or None if processing failed
        """
        try:
            # Extract required fields
            title = raw_json.get("headline", "")
            url = raw_json.get("url", "")

            if not title or not url:
                return None

            # Convert Unix timestamp to datetime
            timestamp = raw_json.get("datetime", 0)
            published_at = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()

            # Build structured data
            processed_data = {
                "title": title,
                "summary": raw_json.get("summary", "")[:500],  # Limit summary length
                "url": url,
                "published_at": published_at.isoformat(),
                "symbols": [symbol.upper()],
                "source_id": None,  # Will need to map or create news source
                "external_id": str(raw_json.get("id", "")),
                "metadata": {
                    "fetch_source": "finnhub",
                    "category": raw_json.get("category", ""),
                    "source_name": raw_json.get("source", ""),
                    "image": raw_json.get("image", ""),
                }
            }

            return processed_data

        except Exception as e:
            print(f"❌ Error processing Finnhub JSON: {e}")
            return None

    def _process_polygon_json(self, raw_json: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """
        Process Polygon JSON format to structured news data.

        Args:
            raw_json: Raw JSON from Polygon API
            symbol: Stock symbol

        Returns:
            Processed news data dict or None if processing failed
        """
        try:
            # Extract required fields
            title = raw_json.get("title", "")
            url = raw_json.get("url", "")

            if not title or not url:
                return None

            # Parse ISO 8601 timestamp
            published_utc = raw_json.get("published_utc", "")
            if published_utc:
                # Polygon uses ISO 8601 format (e.g., "2023-11-18T12:00:00Z")
                try:
                    published_at = datetime.fromisoformat(published_utc.replace('Z', '+00:00'))
                except:
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            # Build structured data
            processed_data = {
                "title": title,
                "summary": raw_json.get("description", "")[:500],  # Limit summary length
                "url": url,
                "published_at": published_at.isoformat(),
                "symbols": [symbol.upper()],
                "source_id": None,
                "external_id": raw_json.get("id", ""),
                "metadata": {
                    "fetch_source": "polygon",
                    "author": raw_json.get("author", ""),
                    "publisher": raw_json.get("publisher", ""),
                    "image_url": raw_json.get("image_url", ""),
                    "amp_url": raw_json.get("amp_url", ""),
                    "tickers": raw_json.get("tickers", []),
                }
            }

            return processed_data

        except Exception as e:
            print(f"❌ Error processing Polygon JSON: {e}")
            return None

    async def process_raw_item(self, raw_item: Dict[str, Any]) -> bool:
        """
        Process a single raw news item and store in stock_news table.

        Args:
            raw_item: Raw news item from database

        Returns:
            True if processing and storage successful
        """
        item_id = raw_item.get("id")
        symbol = raw_item.get("symbol")
        fetch_source = raw_item.get("fetch_source")
        raw_json = raw_item.get("raw_json")

        if not item_id or not symbol:
            return False

        # Update status to processing
        await self.raw_storage.update_processing_status(
            item_id,
            ProcessingStatus.PROCESSING
        )

        try:
            # Process based on fetch source
            processed_data = None

            if fetch_source == "finnhub" and raw_json:
                processed_data = self._process_finnhub_json(raw_json, symbol)
            elif fetch_source == "polygon" and raw_json:
                processed_data = self._process_polygon_json(raw_json, symbol)
            # TODO: Add other sources (newsapi, etc.)

            if not processed_data:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.FAILED,
                    error_log="Failed to extract required fields"
                )
                return False

            # Check if URL already exists in stock_news
            # TODO: Add duplicate check in stock_news table
            # For now, just push to stack

            # Push to stock_news stack
            result = await self.stock_news_db.push_news_to_stack(
                symbol=symbol,
                news_data=processed_data
            )

            if result:
                # Mark as completed
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.COMPLETED
                )
                print(f"✅ Processed and stored news for {symbol}: {processed_data['title'][:50]}...")
                return True
            else:
                await self.raw_storage.update_processing_status(
                    item_id,
                    ProcessingStatus.FAILED,
                    error_log="Failed to push to stock_news table"
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
        Process a batch of unprocessed raw news items.

        Args:
            limit: Maximum number of items to process

        Returns:
            Statistics dict with counts
        """
        stats = {"fetched": 0, "processed": 0, "failed": 0}

        # Get unprocessed items
        unprocessed = await self.raw_storage.get_unprocessed(limit=limit)
        stats["fetched"] = len(unprocessed)

        print(f"📊 Processing {stats['fetched']} unprocessed news items...")

        # Process each item
        for raw_item in unprocessed:
            success = await self.process_raw_item(raw_item)
            if success:
                stats["processed"] += 1
            else:
                stats["failed"] += 1

        print(f"✅ Processing complete: {stats['processed']} succeeded, {stats['failed']} failed")
        return stats
