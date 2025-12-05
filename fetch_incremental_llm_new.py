"""Incremental news fetcher with LLM categorization."""
import asyncio
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client

# EST timezone (UTC-5) - for display only
EST = timezone(timedelta(hours=-5))
UTC = timezone.utc

from src.fetchers.general_news_fetcher import GeneralNewsFetcher
from src.storage.raw_news_storage import RawNewsStorage
from src.storage.fetch_state_manager import FetchStateManager
from src.processors.llm_news_processor import LLMNewsProcessor
from src.services.llm_categorizer import NewsCategorizer
from src.db.stock_news import StockNewsDB
from src.db.data_corrections import DataCorrector
from src.config import LLM_CONFIG, FETCH_CONFIG, TRACKED_COMPANIES, COMPANY_NEWS_CONFIG
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
# change to INFO level for production


async def main():
    """Run incremental news fetch with LLM categorization."""
    logger.debug("=" * 70)
    logger.debug("📰 INCREMENTAL NEWS FETCHER (LLM Categorization)")
    logger.debug("=" * 70)
    now_est = datetime.now(UTC).astimezone(EST)
    print(f"Run time: {now_est.strftime('%Y-%m-%d %H:%M:%S')} EST")
    logger.debug("")
    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    finnhub_api_key = os.getenv("FINNHUB_API_KEY")
    polygon_api_key = os.getenv("MASSIVE_API_KEY")
    zhipu_api_key = os.getenv("ZHIPU_API_KEY")
    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    # Validate
    if not all([finnhub_api_key, polygon_api_key, zhipu_api_key, supabase_url, supabase_key]):
        logger.debug("❌ Missing required environment variables")
        return

    logger.debug("✅ Configuration loaded")
    logger.debug("")
    # Initialize clients
    supabase = create_client(supabase_url, supabase_key)
    general_fetcher = GeneralNewsFetcher(
        finnhub_api_key=finnhub_api_key,
        polygon_api_key=polygon_api_key
    )
    categorizer = NewsCategorizer(api_key=zhipu_api_key)

    # Initialize storage and managers
    raw_storage = RawNewsStorage(client=supabase)
    fetch_state = FetchStateManager(client=supabase)
    stock_news_db = StockNewsDB(client=supabase)
    data_corrector = DataCorrector(client=supabase)
    llm_processor = LLMNewsProcessor(
        stock_news_db=stock_news_db,
        raw_storage=raw_storage,
        categorizer=categorizer
    )

    # ========================================
    # STEP 1: Check for pending raw news and process them first
    # Priority: 1 (Highest - process_pending_raw)
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 1: Check for Pending Raw News (Priority 1)")
    logger.debug("-" * 70)
    pending_count = await raw_storage.count_pending()
    logger.debug(f"📊 Pending raw news items: {pending_count}")
    logger.debug("")
    if pending_count > 0:
        logger.debug(f"⚙️  Processing {pending_count} pending items before fetching new news...")
        logger.debug("")
        total_processed = 0
        total_skipped = 0
        total_failed = 0

        while True:
            batch_stats = await llm_processor.process_unprocessed_batch(
                limit=LLM_CONFIG['processing_limit']
            )

            if batch_stats['fetched'] == 0:
                logger.debug("✅ No more pending items")
                break

            total_processed += batch_stats['processed']
            total_skipped += batch_stats['non_financial_skipped']
            total_failed += batch_stats['failed']

            if batch_stats['categorized'] == 0:
                break

        logger.debug("")
        logger.debug(f"📊 Pending Processing Summary:")
        logger.debug(f"   Categorized & stored: {total_processed}")
        logger.debug(f"   NON_FINANCIAL skipped: {total_skipped}")
        logger.debug(f"   Failed: {total_failed}")
        logger.debug("")
    # ========================================
    # STEP 1.5: Re-process UNCATEGORIZED news in stock_news
    # Priority: 2 (High - recategorize_uncategorized)
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 1.5: Re-process UNCATEGORIZED News (Priority 2)")
    logger.debug("-" * 70)
    uncategorized_count = await stock_news_db.count_uncategorized()
    logger.debug(f"🔄 UNCATEGORIZED news items: {uncategorized_count}")
    logger.debug("")
    if uncategorized_count > 0:
        logger.debug(f"🔄 Re-categorizing {uncategorized_count} UNCATEGORIZED items...")
        logger.debug("")
        total_updated = 0
        total_non_financial = 0
        total_failed_recat = 0

        while True:
            recat_stats = await llm_processor.recategorize_uncategorized_batch(
                limit=LLM_CONFIG['processing_limit']
            )

            if recat_stats['fetched'] == 0:
                logger.debug("✅ No more UNCATEGORIZED items")
                break

            total_updated += recat_stats['updated']
            total_non_financial += recat_stats['non_financial_removed']
            total_failed_recat += recat_stats['failed']

            if recat_stats['recategorized'] == 0:
                break

        logger.debug("")
        logger.debug(f"📊 Re-categorization Summary:")
        logger.debug(f"   Updated: {total_updated}")
        logger.debug(f"   NON_FINANCIAL marked: {total_non_financial}")
        logger.debug(f"   Failed: {total_failed_recat}")
        logger.debug("")
    # ========================================
    # STEP 2: Get Polygon fetch window
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 2: Get Polygon Fetch Window")
    logger.debug("-" * 70)
    polygon_from, polygon_to = await fetch_state.get_last_fetch_time(
        symbol="GENERAL",
        fetch_source="polygon",
        buffer_minutes=FETCH_CONFIG['buffer_minutes']
    )

    # Strip timezone info for date formatting
    if polygon_from.tzinfo:
        polygon_from = polygon_from.replace(tzinfo=None)
    if polygon_to.tzinfo:
        polygon_to = polygon_to.replace(tzinfo=None)

    logger.debug("")
    # ========================================
    # STEP 3: Fetch incremental news
    # Priority: 3 (Normal - fetch_and_process)
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 3: Fetch Incremental News (Priority 3)")
    logger.debug("-" * 70)
    all_items = []

    # Fetch from Finnhub (multiple categories with minId for incremental fetching)
    logger.debug(f"\n🔍 Fetching Finnhub general news...")
    # Get the maximum min_id across all categories to use for fetching
    # This ensures we don't re-fetch news we already have
    max_min_ids = []
    for category in FETCH_CONFIG['finnhub_categories']:
        category_max_id = await fetch_state.get_finnhub_max_id(
            symbol="GENERAL",
            fetch_source=f"finnhub_{category}"
        )
        if category_max_id is not None:
            max_min_ids.append(category_max_id)

    # Use the highest max_id across all categories
    last_min_id = max(max_min_ids) if max_min_ids else 0

    if last_min_id == 0:
        logger.debug(f"   First fetch - starting from minId=0")
    else:
        logger.debug(f"   Incremental fetch - using minId={last_min_id}")
    finnhub_items, finnhub_max_id = await general_fetcher.fetch_finnhub_general_news(
        categories=FETCH_CONFIG['finnhub_categories'],
        min_id=last_min_id
    )
    all_items.extend(finnhub_items)

    # Fetch from Polygon (with full datetime in API call)
    # Polygon expects ISO 8601 format with timezone: YYYY-MM-DDTHH:MM:SSZ
    polygon_from_str = polygon_from.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    polygon_to_str = polygon_to.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    logger.debug(f"\n🔍 Fetching Polygon news ({polygon_from_str} to {polygon_to_str})...")
    polygon_items = await general_fetcher.fetch_polygon_general_news(
        from_date=polygon_from_str,
        to_date=polygon_to_str,
        limit=FETCH_CONFIG['polygon_limit']
    )
    all_items.extend(polygon_items)

    logger.debug("")
    logger.debug(f"📊 Fetch Summary:")
    logger.debug(f"   Finnhub: {len(finnhub_items)} articles")
    logger.debug(f"   Polygon: {len(polygon_items)} articles")
    logger.debug(f"   Total: {len(all_items)} articles")
    logger.debug("")
    # ========================================
    # STEP 3.5: Fetch company-specific news (if enabled)
    # Priority: 3 (Normal - fetch_and_process)
    # ========================================
    if COMPANY_NEWS_CONFIG['enabled']:
        logger.debug("-" * 70)
        logger.info("STEP 3.5: Fetch Company-Specific News (Priority 3)")
        logger.debug("-" * 70)
        logger.debug("")
        company_items = []
        company_fetch_summary = {}

        for symbol, company_name in TRACKED_COMPANIES.items():
            logger.debug(f"🔍 Fetching news for {symbol} ({company_name})...")
            # Get last fetch time for this company
            # Note: fetch_source will be "finnhub_company_{symbol}" to match RawNewsItem
            company_from, company_to = await fetch_state.get_last_fetch_time(
                symbol=symbol,
                fetch_source=f"finnhub_company_{symbol}",
                buffer_minutes=COMPANY_NEWS_CONFIG['buffer_minutes']
            )

            # Strip timezone info
            if company_from.tzinfo:
                company_from = company_from.replace(tzinfo=None)
            if company_to.tzinfo:
                company_to = company_to.replace(tzinfo=None)

            # Fetch company news
            items = await general_fetcher.fetch_company_news(
                symbol=symbol,
                from_timestamp=company_from,
                to_timestamp=company_to
            )

            company_items.extend(items)
            company_fetch_summary[symbol] = len(items)

        all_items.extend(company_items)

        logger.debug("")
        logger.debug(f"📊 Company News Fetch Summary:")
        for symbol, count in company_fetch_summary.items():
            logger.debug(f"   {symbol}: {count} articles")
        logger.debug(f"   Total company news: {len(company_items)} articles")
        logger.debug("")
    # ========================================
    # STEP 4: Store in raw storage
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 4: Store in stock_news_raw")
    logger.debug("-" * 70)
    if all_items:
        storage_stats = await raw_storage.bulk_insert(all_items)
        logger.debug(f"📊 Storage Results:")
        logger.debug(f"   Total: {storage_stats['total']}")
        logger.debug(f"   Inserted: {storage_stats['inserted']}")
        logger.debug(f"   Duplicates: {storage_stats['duplicates']}")
        logger.debug(f"   Failed: {storage_stats['failed']}")
        if storage_stats['inserted'] == 0 and storage_stats['duplicates'] > 0:
            logger.debug(f"   ℹ️  No new updates (all duplicates)")
    else:
        logger.debug("   ℹ️  No news updates")
        storage_stats = {'inserted': 0, 'total': 0}

    logger.debug("")
    # ========================================
    # STEP 5: Update fetch state
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 5: Update Fetch State")
    logger.debug("-" * 70)
    # Update fetch state for each Finnhub category
    # Finnhub only needs max_id tracking, no time windows
    now = datetime.now(UTC).replace(tzinfo=None)  # Current time in UTC
    for category in FETCH_CONFIG['finnhub_categories']:
        category_source = f"finnhub_{category}"
        category_items = [i for i in finnhub_items if i.fetch_source == category_source]

        await fetch_state.update_fetch_state(
            symbol="GENERAL",
            fetch_source=category_source,
            from_time=now,  # Not used for Finnhub, just for record
            to_time=now,    # Not used for Finnhub, just for record
            articles_fetched=len(category_items),
            articles_stored=len(category_items),
            status="success",
            finnhub_max_id=finnhub_max_id  # This is what matters for Finnhub
        )

    if polygon_items:
        # Get max published_at from items (already extracted in RawNewsItem)
        polygon_latest = max(
            (item.published_at for item in polygon_items if item.published_at),
            default=polygon_to
        )
        # Strip timezone if present
        if polygon_latest and polygon_latest.tzinfo:
            polygon_latest = polygon_latest.replace(tzinfo=None)
        elif not polygon_latest:
            polygon_latest = polygon_to
    else:
        polygon_latest = polygon_to

    await fetch_state.update_fetch_state(
        symbol="GENERAL",
        fetch_source="polygon",
        from_time=polygon_from,
        to_time=polygon_latest,
        articles_fetched=len(polygon_items),
        articles_stored=len([i for i in all_items if i.fetch_source == "polygon"]),
        status="success"
    )

    # Update fetch state for company news
    if COMPANY_NEWS_CONFIG['enabled'] and 'company_items' in locals():
        for symbol in TRACKED_COMPANIES.keys():
            symbol_items = [i for i in company_items if i.symbol == symbol]

            if symbol_items:
                # Get max published_at from items
                company_latest = max(
                    (item.published_at for item in symbol_items if item.published_at),
                    default=datetime.now(UTC).replace(tzinfo=None)
                )
                # Strip timezone if present
                if company_latest and company_latest.tzinfo:
                    company_latest = company_latest.replace(tzinfo=None)
            else:
                # No new items, use current time
                company_latest = datetime.now(UTC).replace(tzinfo=None)

            # Get from_time (retrieve it again to ensure we have the value)
            # Note: fetch_source is "finnhub_company_{symbol}" to match RawNewsItem
            company_from, company_to = await fetch_state.get_last_fetch_time(
                symbol=symbol,
                fetch_source=f"finnhub_company_{symbol}",
                buffer_minutes=COMPANY_NEWS_CONFIG['buffer_minutes']
            )

            # Strip timezone info
            if company_from.tzinfo:
                company_from = company_from.replace(tzinfo=None)

            await fetch_state.update_fetch_state(
                symbol=symbol,
                fetch_source=f"finnhub_company_{symbol}",
                from_time=company_from,
                to_time=company_latest,
                articles_fetched=len(symbol_items),
                articles_stored=len(symbol_items),
                status="success"
            )

    logger.debug(f"✅ Updated fetch state for all sources")
    logger.debug(f"   Finnhub max_id: {finnhub_max_id}")
    # Display Polygon time in EST
    polygon_latest_est = polygon_latest.replace(tzinfo=UTC).astimezone(EST)
    logger.debug(f"   Polygon latest: {polygon_latest_est.strftime('%Y-%m-%d %H:%M:%S')} EST")
    if COMPANY_NEWS_CONFIG['enabled'] and 'company_items' in locals():
        logger.debug(f"   Company news: Updated {len(TRACKED_COMPANIES)} companies")
    logger.debug("")
    # ========================================
    # STEP 6: Process with LLM categorization
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 6: LLM Categorization & Processing")
    logger.debug("-" * 70)
    if storage_stats['inserted'] > 0:
        total_processed = 0
        total_skipped = 0
        total_failed = 0

        while True:
            batch_stats = await llm_processor.process_unprocessed_batch(
                limit=LLM_CONFIG['processing_limit']
            )

            if batch_stats['fetched'] == 0:
                logger.debug("✅ No more unprocessed items")
                break

            total_processed += batch_stats['processed']
            total_skipped += batch_stats['non_financial_skipped']
            total_failed += batch_stats['failed']

            if batch_stats['categorized'] == 0:
                break

        logger.debug("")
        logger.debug(f"📊 Processing Summary:")
        logger.debug(f"   Categorized & stored: {total_processed}")
        logger.debug(f"   NON_FINANCIAL skipped: {total_skipped}")
        logger.debug(f"   Failed: {total_failed}")
    else:
        logger.debug("⚠️  No new articles to process")
        total_processed = 0
        total_skipped = 0

    logger.debug("")
    # ========================================
    # STEP 6.5: Data Corrections
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 6.5: Database Corrections")
    logger.debug("-" * 70)
    correction_stats = await data_corrector.correct_empty_strings_in_stock_news()

    logger.debug("")
    # ========================================
    # STEP 7: Show sample categorized news
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 7: Recent Categorized News")
    logger.debug("-" * 70)
    if total_processed > 0:
        # Get recent news
        def _get_recent():
            return (
                supabase
                .table("stock_news")
                .select("title, category, secondary_category, source, published_at")
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )

        recent = await asyncio.to_thread(_get_recent)

        if recent.data:
            logger.debug("\nRecent News:")
            for item in recent.data:
                cat = item.get('category', 'N/A')
                sec_cat = item.get('secondary_category', '')
                title = item.get('title', '')[:60]
                logger.debug(f"\n[{cat}]")
                if sec_cat:
                    logger.debug(f"  Stocks: {sec_cat}")
                logger.debug(f"  {title}...")
    logger.debug("")
    # ========================================
    # STEP 8: Final statistics
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 8: Summary")
    logger.debug("-" * 70)
    raw_stats = await raw_storage.get_stats()

    logger.debug(f"📊 Raw Storage:")
    logger.debug(f"   Total: {raw_stats['total']}")
    logger.debug(f"   Pending: {raw_stats['pending']}")
    logger.debug(f"   Completed: {raw_stats['completed']}")
    logger.debug(f"   Failed: {raw_stats['failed']}")
    logger.debug("")
    logger.debug(f"📊 This Run:")
    logger.debug(f"   Articles fetched: {len(all_items)}")
    logger.debug(f"   Articles stored (raw): {storage_stats['inserted']}")
    logger.debug(f"   Articles categorized: {total_processed + total_skipped}")
    logger.debug(f"   Financial news stored: {total_processed}")
    logger.debug(f"   NON_FINANCIAL filtered: {total_skipped}")
    logger.debug("")
    # Cleanup
    await general_fetcher.close()
    await categorizer.close()

    logger.debug("=" * 70)
    logger.info("✅ INCREMENTAL FETCH COMPLETE")
    logger.debug("=" * 70)
    logger.debug(f"💡 Next run will fetch:")
    logger.debug(f"   Finnhub: news with ID > {finnhub_max_id}")
    # Display in EST
    polygon_latest_est = polygon_latest.replace(tzinfo=UTC).astimezone(EST)
    logger.debug(f"   Polygon: news after {polygon_latest_est.strftime('%Y-%m-%d %H:%M:%S')} EST")
    logger.debug("")
    
if __name__ == "__main__":
    asyncio.run(main())
