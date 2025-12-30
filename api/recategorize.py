"""Re-categorize existing news items (pending raw + invalid categories)."""
# Add api directory to path so src module can be found (must be first)
import sys
from pathlib import Path
_api_dir = str(Path(__file__).parent.resolve())
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

import asyncio
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client

# EST timezone (UTC-5) - for display only
EST = timezone(timedelta(hours=-5))
UTC = timezone.utc

from src.storage.raw_news_storage import RawNewsStorage
from src.processors.llm_news_processor import LLMNewsProcessor
from src.services.llm_categorizer import NewsCategorizer
from src.db.stock_news import StockNewsDB
from src.config import LLM_CONFIG
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
# Set httpx logging to WARNING to suppress HTTP request logs
logging.getLogger("httpx").setLevel(logging.WARNING)


async def main():
    """Re-categorize existing news items with validation and LLM processing."""
    logger.info("=" * 70)
    logger.info("RE-CATEGORIZATION SERVICE")
    logger.info("=" * 70)
    now_est = datetime.now(UTC).astimezone(EST)
    logger.info(f"Run time: {now_est.strftime('%Y-%m-%d %H:%M:%S')} EST")
    logger.debug("")

    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    zhipu_api_key = os.getenv("ZHIPU_API_KEY")
    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    # Validate
    if not all([zhipu_api_key, supabase_url, supabase_key]):
        logger.info("Missing required environment variables")
        return

    logger.info("Configuration loaded")
    logger.debug("")

    # Initialize clients
    supabase = create_client(supabase_url, supabase_key)
    categorizer = NewsCategorizer(api_key=zhipu_api_key)

    # Initialize storage and managers
    raw_storage = RawNewsStorage(client=supabase)
    stock_news_db = StockNewsDB(client=supabase)
    llm_processor = LLMNewsProcessor(
        stock_news_db=stock_news_db,
        raw_storage=raw_storage,
        categorizer=categorizer
    )

    # ========================================
    # STEP 0: Retry Failed Raw News
    # Priority: 0 (Highest - retry failed items)
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 0: Retry Failed Raw News (Priority 0)")
    logger.debug("-" * 70)

    # Get detailed stats for debugging
    raw_stats_initial = await raw_storage.get_stats()
    logger.info(f"Initial raw storage stats:")
    logger.info(f"   Total: {raw_stats_initial['total']}")
    logger.info(f"   Pending: {raw_stats_initial['pending']}")
    logger.info(f"   Completed: {raw_stats_initial['completed']}")
    logger.info(f"   Failed: {raw_stats_initial['failed']}")
    logger.debug("")

    failed_count = raw_stats_initial['failed']
    if failed_count > 0:
        logger.info(f"Resetting {min(failed_count, LLM_CONFIG['processing_limit'])} failed items to pending...")
        reset_count = await raw_storage.reset_failed_to_pending(limit=failed_count)
        logger.info(f"Reset {reset_count} failed items to pending for retry")
        logger.debug("")

    # ========================================
    # STEP 1: Process Pending Raw News
    # Priority: 1 (High - process_pending_raw)
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 1: Process Pending Raw News (Priority 1)")
    logger.debug("-" * 70)
    pending_count = await raw_storage.count_pending()
    logger.info(f"Pending raw news items: {pending_count}")
    logger.debug("")

    if pending_count > 0:
        logger.info(f"Processing {pending_count} pending items...")
        logger.debug("")
        total_processed = 0
        total_skipped = 0
        total_failed = 0

        while True:
            batch_stats = await llm_processor.process_unprocessed_batch(
                limit=LLM_CONFIG['processing_limit']
            )

            if batch_stats['fetched'] == 0:
                logger.debug("No more pending items")
                break

            total_processed += batch_stats['processed']
            total_skipped += batch_stats['excluded_skipped']
            total_failed += batch_stats['failed']

            if batch_stats['categorized'] == 0:
                break

        logger.debug("")
        logger.info(f"Pending Processing Summary:")
        logger.info(f"   Categorized & stored: {total_processed}")
        logger.info(f"   NON_FINANCIAL skipped: {total_skipped}")
        logger.info(f"   Failed: {total_failed}")
        logger.debug("")

    # ========================================
    # STEP 2: Validate & Fix Categories
    # Priority: 2 (High - category validation and correction)
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 2: Validate & Fix Categories (Priority 2)")
    logger.debug("-" * 70)

    # Check all items needing re-categorization (unified query)
    items_needing_fix = await stock_news_db.count_items_needing_recategorization()
    logger.info(f"Items needing re-categorization: {items_needing_fix}")
    logger.debug("")

    if items_needing_fix > 0:
        # ========================================
        # STEP 2a: Pre-filter "nobody" categories ONCE
        # ========================================
        logger.info(f"Pre-filtering 'nobody' categories...")
        nobody_filtered = await llm_processor.prefilter_nobody_categories()

        if nobody_filtered > 0:
            logger.info(f"Pre-filtered {nobody_filtered} 'nobody' categories → NON_FINANCIAL")
            logger.debug("")

        # ========================================
        # STEP 2a2: Normalize categories with spaces
        # ========================================
        logger.info(f"Normalizing categories with spaces...")
        space_normalized = await llm_processor.normalize_space_categories()

        if space_normalized > 0:
            logger.info(f"Normalized {space_normalized} categories (spaces → underscores)")
            logger.debug("")

        # ========================================
        # STEP 2b: Process remaining items with LLM in batches
        # ========================================
        # Re-count after pre-filtering and normalization
        remaining_items = await stock_news_db.count_items_needing_recategorization()

        if remaining_items > 0:
            logger.info(f"Re-categorizing {remaining_items} remaining items with LLM...")
            logger.debug("")

            # Unified statistics
            total_updated = 0
            total_non_financial = 0
            total_failed_recat = 0

            # Process remaining items in batches
            while True:
                recat_stats = await llm_processor.recategorize_batch(
                    limit=LLM_CONFIG['processing_limit']
                )

                if recat_stats['fetched'] == 0:
                    logger.debug("No more items needing re-categorization")
                    break

                total_updated += recat_stats['updated']
                total_non_financial += recat_stats['excluded_marked']
                total_failed_recat += recat_stats['failed']

                if recat_stats['recategorized'] == 0:
                    break

            logger.debug("")
            logger.info(f"LLM Re-categorization Summary:")
            logger.info(f"   LLM processed: {total_updated}")
            logger.info(f"   NON_FINANCIAL (from LLM): {total_non_financial}")
            logger.info(f"   Failed: {total_failed_recat}")
            logger.debug("")

        # ========================================
        # Combined Summary
        # ========================================
        logger.info(f"Category Validation Summary:")
        logger.info(f"   Pre-filtered (nobody): {nobody_filtered}")
        logger.info(f"   Normalized (spaces): {space_normalized}")
        logger.info(f"   LLM updated: {total_updated if remaining_items > 0 else 0}")
        logger.info(f"   Total fixed: {nobody_filtered + space_normalized + (total_updated if remaining_items > 0 else 0)}")
        logger.debug("")

    # Cleanup
    await categorizer.close()

    # Final statistics
    final_failed = await raw_storage.count_failed()
    final_pending = await raw_storage.count_pending()

    logger.info("=" * 70)
    logger.info("RE-CATEGORIZATION COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Remaining failed items: {final_failed}")
    logger.info(f"Remaining pending items: {final_pending}")
    logger.debug("")


if __name__ == "__main__":
    asyncio.run(main())
