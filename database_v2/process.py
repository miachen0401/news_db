"""
Process raw news: extract data then classify with LLM.

This is the main script that orchestrates the entire pipeline:
1. Extract structured data from raw_json
2. Classify extracted news with LLM
"""
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from supabase import create_client

from config import LLM_MODELS
from db import StockProcessDB
from processors import EventClassifier, NewsExtractor

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def classify_batch(db: StockProcessDB, classifier: EventClassifier, news_items: list) -> Dict[str, int]:
    """Classify a batch of news items with LLM."""
    stats = {
        "total": len(news_items),
        "classified": 0,
        "event_based": 0,
        "not_event_based": 0,
        "failed": 0
    }

    batch_size = classifier.batch_size
    delay = LLM_MODELS["categorization"]["delay_between_batches"]

    for i in range(0, len(news_items), batch_size):
        batch = news_items[i:i + batch_size]
        summaries = [item["summary"] for item in batch]

        logger.info(f"Classifying batch of {len(summaries)} news items...")
        start_time = time.time()
        classifications = await classifier.classify_news_batch(summaries)
        processing_time_ms = int((time.time() - start_time) * 1000)

        for item, (event_based, reasoning, error) in zip(batch, classifications):
            if event_based is not None:
                success = await db.update_classification(
                    record_id=item["id"],
                    event_based=event_based,
                    reasoning=reasoning,
                    model_used=classifier.model_config["model"],
                    processing_time_ms=processing_time_ms
                )

                if success:
                    stats["classified"] += 1
                    if event_based:
                        stats["event_based"] += 1
                    else:
                        stats["not_event_based"] += 1
                else:
                    stats["failed"] += 1
            else:
                stats["failed"] += 1
                logger.warning(f"Failed to classify: {item['title'][:60] if item.get('title') else item['summary'][:60]}... Error: {error}")

        if i + batch_size < len(news_items):
            logger.info(f"Processed {min(i + batch_size, len(news_items))}/{len(news_items)}, waiting {delay}s...")
            await asyncio.sleep(delay)

    return stats


async def main():
    """Main entry point."""
    logger.info("=" * 70)
    logger.info("NEWS PROCESSING PIPELINE")
    logger.info("=" * 70)

    # Load environment
    env_path = Path(__file__).parent.parent / "api" / ".env"
    load_dotenv(env_path)

    zhipu_api_key = os.getenv("ZHIPU_API_KEY")
    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    if not all([zhipu_api_key, supabase_url, supabase_key]):
        logger.error("Missing required environment variables")
        return

    # Initialize
    supabase = create_client(supabase_url, supabase_key)
    db = StockProcessDB(supabase_client=supabase)
    extractor = NewsExtractor(db=db)
    classifier = EventClassifier(api_key=zhipu_api_key)

    # Parse arguments
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        logger.info("\nSelect processing mode:")
        logger.info("  1. Test mode (last 100 least recent news)")
        logger.info("  2. Production mode (all news after 2024-12-20)")
        choice = input("\nEnter choice (1 or 2): ").strip()
        mode = "test" if choice == "1" else "production"

    logger.info(f"\nMode: {mode}\n")

    # STEP 1: EXTRACT
    logger.info("=" * 70)
    logger.info("STEP 1: EXTRACTING DATA FROM RAW NEWS")
    logger.info("=" * 70)

    if mode == "test":
        raw_news = await db.fetch_raw_news(mode="test", limit=100)
    else:
        raw_news = await db.fetch_raw_news(mode="production", after_date="2024-12-20")

    if not raw_news:
        logger.info("No news to extract")
        await classifier.close()
        return

    logger.info(f"Extracting data from {len(raw_news)} news articles...")
    extract_stats = await extractor.extract_and_save(raw_news)

    logger.info("")
    logger.info("Extraction Summary:")
    logger.info(f"  Total fetched: {extract_stats['total']}")
    logger.info(f"  Extracted: {extract_stats['extracted']}")
    logger.info(f"  Skipped (no summary): {extract_stats['skipped_no_summary']}")
    logger.info(f"  Skipped (duplicate): {extract_stats['skipped_duplicate']}")
    logger.info(f"  Failed: {extract_stats['failed']}")
    logger.info("")

    # STEP 2: CLASSIFY
    logger.info("=" * 70)
    logger.info("STEP 2: CLASSIFYING WITH LLM")
    logger.info("=" * 70)

    # Fetch unclassified news
    unclassified = await db.fetch_unclassified_news(limit=None)

    if not unclassified:
        logger.info("No unclassified news to process")
        await classifier.close()
        return

    logger.info(f"Classifying {len(unclassified)} unclassified news articles...")
    classify_stats = await classify_batch(db, classifier, unclassified)

    logger.info("")
    logger.info("Classification Summary:")
    logger.info(f"  Total unclassified: {classify_stats['total']}")
    logger.info(f"  Successfully classified: {classify_stats['classified']}")
    logger.info(f"    - Event-based: {classify_stats['event_based']}")
    logger.info(f"    - Not event-based: {classify_stats['not_event_based']}")
    logger.info(f"  Failed: {classify_stats['failed']}")
    logger.info("")

    # FINAL SUMMARY
    logger.info("=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Extracted: {extract_stats['extracted']} news")
    logger.info(f"Classified: {classify_stats['classified']} news")
    logger.info(f"  Event-based: {classify_stats['event_based']}")
    logger.info(f"  Not event-based: {classify_stats['not_event_based']}")
    logger.info("")

    await classifier.close()


if __name__ == "__main__":
    asyncio.run(main())
