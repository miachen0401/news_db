"""Initial database setup - fetch news for a specific date with LLM categorization.

Use this script when starting with a new/empty database.
It fetches news for a specific date and records the timestamp for incremental fetching.

Default: 2025-11-22 (change TARGET_DATE variable to fetch different date)
"""
import asyncio
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

from fetchers.general_news_fetcher import GeneralNewsFetcher
from storage.raw_news_storage import RawNewsStorage
from storage.fetch_state_manager import FetchStateManager
from processors.llm_news_processor import LLMNewsProcessor
from services.llm_categorizer import NewsCategorizer
from db.stock_news import StockNewsDB


# ============================================
# CONFIGURATION: Change this date as needed
# ============================================
TARGET_DATE = "2025-11-22"  # Format: YYYY-MM-DD


async def main():
    """Fetch news for specific date with LLM categorization."""
    print("=" * 70)
    print("📰 INITIAL DATABASE SETUP - LLM CATEGORIZATION")
    print("=" * 70)
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

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
        print("❌ Missing required environment variables")
        return

    print("✅ Configuration loaded")
    print()

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
    llm_processor = LLMNewsProcessor(
        stock_news_db=stock_news_db,
        raw_storage=raw_storage,
        categorizer=categorizer
    )

    print(f"📅 Target Date: {TARGET_DATE}")
    print(f"   Fetching all news from this date")
    print()

    # ========================================
    # STEP 1: Fetch general news for target date
    # ========================================
    print("-" * 70)
    print("STEP 1: Fetch General News")
    print("-" * 70)

    all_items = []

    # Fetch from Finnhub (general news, client-side filtering)
    print(f"\n🔍 Fetching Finnhub general news...")
    # Parse target date for filtering
    target_dt = datetime.strptime(TARGET_DATE, "%Y-%m-%d")
    finnhub_items = await general_fetcher.fetch_finnhub_general_news(
        after_timestamp=target_dt  # Filter to get news from this date onwards
    )
    all_items.extend(finnhub_items)

    # Fetch from Polygon (with full date range)
    polygon_from_str = f"{TARGET_DATE}T00:00:00Z"
    polygon_to_str = f"{TARGET_DATE}T23:59:59Z"

    print(f"\n🔍 Fetching Polygon news ({TARGET_DATE})...")
    polygon_items = await general_fetcher.fetch_polygon_general_news(
        from_date=polygon_from_str,
        to_date=polygon_to_str,
        limit=100
    )
    all_items.extend(polygon_items)

    print()
    print(f"📊 Fetch Summary:")
    print(f"   Finnhub: {len(finnhub_items)} articles")
    print(f"   Polygon: {len(polygon_items)} articles")
    print(f"   Total: {len(all_items)} articles")
    print()

    # ========================================
    # STEP 2: Store in raw storage
    # ========================================
    print("-" * 70)
    print("STEP 2: Store in stock_news_raw")
    print("-" * 70)

    if all_items:
        storage_stats = await raw_storage.bulk_insert(all_items)
        print(f"📊 Storage Results:")
        print(f"   Total: {storage_stats['total']}")
        print(f"   Inserted: {storage_stats['inserted']}")
        print(f"   Duplicates: {storage_stats['duplicates']}")
        print(f"   Failed: {storage_stats['failed']}")

        if storage_stats['inserted'] == 0 and storage_stats['duplicates'] > 0:
            print(f"   ℹ️  No new updates (all duplicates)")
    else:
        print("   ℹ️  No news fetched")
        storage_stats = {'inserted': 0, 'total': 0}

    print()

    # ========================================
    # STEP 3: Update fetch state
    # ========================================
    print("-" * 70)
    print("STEP 3: Update Fetch State")
    print("-" * 70)

    # Calculate actual latest news timestamps from fetched items
    if finnhub_items:
        # Get max published_at from items (already extracted in RawNewsItem)
        finnhub_latest = max(
            (item.published_at for item in finnhub_items if item.published_at),
            default=target_dt
        )
        # Strip timezone if present
        if finnhub_latest and finnhub_latest.tzinfo:
            finnhub_latest = finnhub_latest.replace(tzinfo=None)
        elif not finnhub_latest:
            finnhub_latest = target_dt
    else:
        finnhub_latest = target_dt

    if polygon_items:
        # Get max published_at from items (already extracted in RawNewsItem)
        polygon_latest = max(
            (item.published_at for item in polygon_items if item.published_at),
            default=target_dt
        )
        # Strip timezone if present
        if polygon_latest and polygon_latest.tzinfo:
            polygon_latest = polygon_latest.replace(tzinfo=None)
        elif not polygon_latest:
            polygon_latest = target_dt
    else:
        polygon_latest = target_dt

    await fetch_state.update_fetch_state(
        symbol="GENERAL",
        fetch_source="finnhub",
        from_time=target_dt,
        to_time=finnhub_latest,
        articles_fetched=len(finnhub_items),
        articles_stored=len([i for i in all_items if i.fetch_source == "finnhub"]),
        status="success"
    )

    await fetch_state.update_fetch_state(
        symbol="GENERAL",
        fetch_source="polygon",
        from_time=target_dt,
        to_time=polygon_latest,
        articles_fetched=len(polygon_items),
        articles_stored=len([i for i in all_items if i.fetch_source == "polygon"]),
        status="success"
    )

    print(f"✅ Updated fetch state for both sources")
    print(f"   Finnhub latest: {finnhub_latest.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Polygon latest: {polygon_latest.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ========================================
    # STEP 4: Process with LLM categorization
    # ========================================
    print("-" * 70)
    print("STEP 4: LLM Categorization & Processing")
    print("-" * 70)

    if storage_stats['inserted'] > 0:
        total_processed = 0
        total_skipped = 0
        total_failed = 0

        while True:
            batch_stats = await llm_processor.process_unprocessed_batch(limit=20)

            if batch_stats['fetched'] == 0:
                print("✅ No more unprocessed items")
                break

            total_processed += batch_stats['processed']
            total_skipped += batch_stats['non_financial_skipped']
            total_failed += batch_stats['failed']

            if batch_stats['categorized'] == 0:
                break

        print()
        print(f"📊 Processing Summary:")
        print(f"   Categorized & stored: {total_processed}")
        print(f"   NON_FINANCIAL skipped: {total_skipped}")
        print(f"   Failed: {total_failed}")
    else:
        print("⚠️  No new articles to process")
        total_processed = 0
        total_skipped = 0

    print()

    # ========================================
    # STEP 5: Show sample categorized news
    # ========================================
    print("-" * 70)
    print("STEP 5: Recent Categorized News")
    print("-" * 70)

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
            print("\nRecent News:")
            for item in recent.data:
                cat = item.get('category', 'N/A')
                sec_cat = item.get('secondary_category', '')
                title = item.get('title', '')[:60]
                print(f"\n[{cat}]")
                if sec_cat:
                    print(f"  Stocks: {sec_cat}")
                print(f"  {title}...")

    print()

    # ========================================
    # STEP 6: Final statistics
    # ========================================
    print("-" * 70)
    print("STEP 6: Summary")
    print("-" * 70)

    raw_stats = await raw_storage.get_stats()

    print(f"📊 Raw Storage:")
    print(f"   Total: {raw_stats['total']}")
    print(f"   Pending: {raw_stats['pending']}")
    print(f"   Completed: {raw_stats['completed']}")
    print(f"   Failed: {raw_stats['failed']}")
    print()

    print(f"📊 This Run:")
    print(f"   Articles fetched: {len(all_items)}")
    print(f"   Articles stored (raw): {storage_stats['inserted']}")
    print(f"   Articles categorized: {total_processed + total_skipped}")
    print(f"   Financial news stored: {total_processed}")
    print(f"   NON_FINANCIAL filtered: {total_skipped}")
    print()

    # Cleanup
    await general_fetcher.close()
    await categorizer.close()

    print("=" * 70)
    print("✅ INITIAL DATABASE SETUP COMPLETE")
    print("=" * 70)
    print(f"💡 Next run will fetch news after:")
    print(f"   Finnhub: {finnhub_latest.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Polygon: {polygon_latest.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("🚀 Use fetch_incremental_llm.py for ongoing incremental updates")
    print()


if __name__ == "__main__":
    asyncio.run(main())
