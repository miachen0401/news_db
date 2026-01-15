"""Extract structured data from raw news."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class NewsExtractor:
    """Extract structured data from raw_json in stock_news_raw."""

    def __init__(self, db):
        """Initialize with database client."""
        self.db = db

    def extract_title(self, raw_json: Dict) -> Optional[str]:
        """Extract title from raw_json (handles different API formats)."""
        if not raw_json or not isinstance(raw_json, dict):
            return None
        return raw_json.get("title") or raw_json.get("headline")

    def extract_source(self, raw_json: Dict) -> Optional[str]:
        """Extract source from raw_json (handles different API formats)."""
        if not raw_json or not isinstance(raw_json, dict):
            return None

        # Try direct source field first
        source = raw_json.get("source")

        # If not found, try publisher.name (Polygon format)
        if not source and raw_json.get("publisher"):
            publisher = raw_json["publisher"]
            if isinstance(publisher, dict):
                source = publisher.get("name")

        return source

    def extract_summary(self, raw_news: Dict) -> Optional[str]:
        """Extract summary from metadata or raw_json."""
        summary = None

        # Try to get summary from metadata
        if raw_news.get("metadata") and isinstance(raw_news["metadata"], dict):
            summary = raw_news["metadata"].get("summary")

        # If no summary in metadata, try raw_json
        if not summary and raw_news.get("raw_json") and isinstance(raw_news["raw_json"], dict):
            summary = raw_news["raw_json"].get("description") or raw_news["raw_json"].get("summary")

        return summary

    async def extract_and_save(self, raw_news: List[Dict]) -> Dict[str, int]:
        """
        Extract data from raw news and save to stock_process_v1.

        Args:
            raw_news: List of raw news items from stock_news_raw

        Returns:
            Statistics dictionary
        """
        stats = {
            "total": len(raw_news),
            "extracted": 0,
            "skipped_no_summary": 0,
            "skipped_duplicate": 0,
            "failed": 0
        }

        # List to collect news without summaries
        no_summary_items = []

        for item in raw_news:
            try:
                # Extract summary first (required field)
                summary = self.extract_summary(item)
                if not summary:
                    stats["skipped_no_summary"] += 1
                    logger.debug(f"Skipping news without summary: {item.get('url', 'unknown')}")

                    # Collect for logging
                    no_summary_items.append({
                        "id": item.get("id"),
                        "url": item.get("url"),
                        "fetch_source": item.get("fetch_source"),
                        "raw_json": item.get("raw_json")
                    })
                    continue

                # Check if already processed
                content_hash = item.get("content_hash")
                if content_hash and await self.db.check_existing(content_hash):
                    stats["skipped_duplicate"] += 1
                    logger.debug(f"Skipping already processed: {content_hash}")
                    continue

                # Extract all fields
                raw_json = item.get("raw_json")
                title = self.extract_title(raw_json)
                source = self.extract_source(raw_json)

                # Prepare record (without classification - that comes later)
                record = {
                    "raw_news_id": item["id"],
                    "symbol": None,  # Will be populated later if needed
                    "title": title,
                    "summary": summary,
                    "url": item["url"],
                    "source": source,
                    "published_at": item["published_at"],
                    "fetch_source": item.get("fetch_source"),
                    "content_hash": content_hash,
                    "event_based": None,  # Not classified yet
                    "llm_reasoning": None,
                    "model_used": None,
                    "processing_time_ms": None,
                    "error_log": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }

                # Insert into stock_process_v1
                success = await self.db.insert_extracted_news(record)

                if success:
                    stats["extracted"] += 1
                    logger.debug(f"✓ Extracted: {title[:60] if title else summary[:60]}...")
                else:
                    stats["failed"] += 1

            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"Failed to extract: {e}")

        # Save news without summaries to log file
        if no_summary_items:
            log_dir = Path(__file__).parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"no_summary_{timestamp}.json"

            with open(log_file, 'w') as f:
                json.dump({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "count": len(no_summary_items),
                    "items": no_summary_items
                }, f, indent=2)

            logger.info(f"Saved {len(no_summary_items)} news without summaries to {log_file}")

        return stats
