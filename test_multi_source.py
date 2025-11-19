"""Test script for multi-source news fetching (Finnhub + Polygon)."""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

from fetchers.finnhub_fetcher import FinnhubNewsFetcher
from fetchers.polygon_fetcher import PolygonNewsFetcher
from storage.raw_news_storage import RawNewsStorage
from processors.news_processor import NewsProcessor
from db.stock_news import StockNewsDB


async def main():
    """Main test function."""
    print("=" * 60)
    print("📰 MULTI-SOURCE NEWS FETCHING TEST")
    print("=" * 60)

    # Load environment variables
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    # Get API keys and Supabase credentials
    finnhub_api_key = os.getenv("FINNHUB_API_KEY")
    polygon_api_key = os.getenv("MASSIVE_API_KEY")
    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    if not finnhub_api_key:
        print("❌ FINNHUB_API_KEY not found in .env file")
        return

    if not polygon_api_key:
        print("❌ MASSIVE_API_KEY not found in .env file")
        return

    if not supabase_url or not supabase_key:
        print("❌ Supabase credentials not found in .env file")
        return

    print(f"✅ Loaded configuration")
    print(f"   - Finnhub API Key: {finnhub_api_key[:10]}...")
    print(f"   - Polygon API Key: {polygon_api_key[:10]}...")
    print(f"   - Supabase URL: {supabase_url}")
    print()

    # Initialize Supabase client
    supabase_client = create_client(supabase_url, supabase_key)
    print("✅ Supabase client initialized")

    # Initialize components
    finnhub_fetcher = FinnhubNewsFetcher(api_key=finnhub_api_key)
    polygon_fetcher = PolygonNewsFetcher(api_key=polygon_api_key)
    raw_storage = RawNewsStorage(client=supabase_client)
    stock_news_db = StockNewsDB(client=supabase_client)
    processor = NewsProcessor(stock_news_db=stock_news_db, raw_storage=raw_storage)

    print("✅ Components initialized")
    print()

    # Test symbols
    test_symbols = ["AAPL", "TSLA"]

    # ========================================
    # STEP 1: Fetch news from Finnhub
    # ========================================
    print("-" * 60)
    print("STEP 1: Fetching news from Finnhub")
    print("-" * 60)

    finnhub_items = []
    for symbol in test_symbols:
        items = await finnhub_fetcher.fetch_for_symbol(symbol=symbol, days_back=7)
        finnhub_items.extend(items)
        print(f"   {symbol}: {len(items)} articles")

    print(f"\n📊 Finnhub total: {len(finnhub_items)} articles")
    print()

    # ========================================
    # STEP 2: Fetch news from Polygon
    # ========================================
    print("-" * 60)
    print("STEP 2: Fetching news from Polygon")
    print("-" * 60)

    polygon_items = []
    for symbol in test_symbols:
        items = await polygon_fetcher.fetch_for_symbol(symbol=symbol, days_back=7, limit=20)
        polygon_items.extend(items)
        print(f"   {symbol}: {len(items)} articles")

    print(f"\n📊 Polygon total: {len(polygon_items)} articles")
    print()

    # ========================================
    # STEP 3: Store all in stock_news_raw
    # ========================================
    print("-" * 60)
    print("STEP 3: Storing in stock_news_raw table")
    print("-" * 60)

    all_items = finnhub_items + polygon_items
    print(f"Total items to store: {len(all_items)}")
    print(f"  - Finnhub: {len(finnhub_items)}")
    print(f"  - Polygon: {len(polygon_items)}")
    print()

    if all_items:
        insert_stats = await raw_storage.bulk_insert(all_items)
        print(f"\n📊 Insert Statistics:")
        print(f"   Total: {insert_stats['total']}")
        print(f"   Inserted: {insert_stats['inserted']}")
        print(f"   Duplicates: {insert_stats['duplicates']}")
        print(f"   Failed: {insert_stats['failed']}")
    else:
        print("⚠️  No articles to insert")

    print()

    # ========================================
    # STEP 4: Get storage statistics by source
    # ========================================
    print("-" * 60)
    print("STEP 4: Raw storage statistics by source")
    print("-" * 60)

    stats = await raw_storage.get_stats()
    print(f"📊 Stock News Raw Table:")
    print(f"   Total: {stats['total']}")
    print(f"   Pending: {stats['pending']}")
    print(f"   Completed: {stats['completed']}")
    print(f"   Failed: {stats['failed']}")
    print()

    # ========================================
    # STEP 5: Process unprocessed news
    # ========================================
    print("-" * 60)
    print("STEP 5: Processing raw news into stock_news table")
    print("-" * 60)

    # Process all pending items
    total_processed = 0
    total_failed = 0
    batch_size = 50

    while True:
        batch_stats = await processor.process_unprocessed_batch(limit=batch_size)

        if batch_stats['fetched'] == 0:
            print("✅ No more unprocessed items")
            break

        total_processed += batch_stats['processed']
        total_failed += batch_stats['failed']

        print(f"Batch: {batch_stats['processed']} succeeded, {batch_stats['failed']} failed")

        if batch_stats['processed'] == 0:
            print("⚠️  All items in batch failed - stopping")
            break

    print(f"\n📊 Processing Statistics:")
    print(f"   Processed: {total_processed}")
    print(f"   Failed: {total_failed}")
    print()

    # ========================================
    # STEP 6: View processed news stacks
    # ========================================
    print("-" * 60)
    print("STEP 6: Viewing processed news stacks")
    print("-" * 60)

    for symbol in test_symbols:
        news_stack = await stock_news_db.get_news_stack(symbol=symbol, limit=5)
        print(f"\n{symbol} News Stack ({len(news_stack)} articles):")
        for idx, article in enumerate(news_stack, 1):
            title = article.get('title', 'No title')[:60]
            position = article.get('position_in_stack', '?')
            source = article.get('metadata', {}).get('fetch_source', 'unknown')
            print(f"   [{position}] ({source}) {title}...")

    print()

    # ========================================
    # STEP 7: Final statistics
    # ========================================
    print("-" * 60)
    print("STEP 7: Final statistics")
    print("-" * 60)

    final_stats = await raw_storage.get_stats()
    print(f"📊 Final Raw Storage Stats:")
    print(f"   Total: {final_stats['total']}")
    print(f"   Pending: {final_stats['pending']}")
    print(f"   Completed: {final_stats['completed']}")
    print(f"   Failed: {final_stats['failed']}")

    # Cleanup
    await finnhub_fetcher.close()
    await polygon_fetcher.close()

    print()
    print("=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
