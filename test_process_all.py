"""Process all unprocessed news items."""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

from storage.raw_news_storage import RawNewsStorage
from processors.news_processor import NewsProcessor
from db.stock_news import StockNewsDB


async def main():
    """Process all pending news items."""
    print("=" * 60)
    print("📰 PROCESSING ALL UNPROCESSED NEWS")
    print("=" * 60)
    print()

    # Load environment variables
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    # Get Supabase credentials
    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    if not supabase_url or not supabase_key:
        print("❌ Supabase credentials not found in .env file")
        return

    print(f"✅ Loaded configuration")
    print()

    # Initialize Supabase client
    supabase_client = create_client(supabase_url, supabase_key)

    # Initialize components
    raw_storage = RawNewsStorage(client=supabase_client)
    stock_news_db = StockNewsDB(client=supabase_client)
    processor = NewsProcessor(stock_news_db=stock_news_db, raw_storage=raw_storage)

    print("✅ Components initialized")
    print()

    # Get initial statistics
    print("-" * 60)
    print("Initial Statistics")
    print("-" * 60)

    stats = await raw_storage.get_stats()
    print(f"📊 Stock News Raw Table:")
    print(f"   Total: {stats['total']}")
    print(f"   Pending: {stats['pending']}")
    print(f"   Completed: {stats['completed']}")
    print(f"   Failed: {stats['failed']}")
    print()

    # Process all pending items
    print("-" * 60)
    print("Processing All Unprocessed News")
    print("-" * 60)

    total_processed = 0
    total_failed = 0
    batch_size = 50

    while True:
        # Process in batches
        batch_stats = await processor.process_unprocessed_batch(limit=batch_size)

        if batch_stats['fetched'] == 0:
            print("✅ No more unprocessed items")
            break

        total_processed += batch_stats['processed']
        total_failed += batch_stats['failed']

        print(f"Batch: {batch_stats['processed']} succeeded, {batch_stats['failed']} failed")

        # Stop if nothing was processed (all failed)
        if batch_stats['processed'] == 0:
            print("⚠️  All items in batch failed - stopping")
            break

    print()
    print(f"📊 Total Processing Results:")
    print(f"   Processed: {total_processed}")
    print(f"   Failed: {total_failed}")
    print()

    # Get final statistics
    print("-" * 60)
    print("Final Statistics")
    print("-" * 60)

    final_stats = await raw_storage.get_stats()
    print(f"📊 Stock News Raw Table:")
    print(f"   Total: {final_stats['total']}")
    print(f"   Pending: {final_stats['pending']}")
    print(f"   Completed: {final_stats['completed']}")
    print(f"   Failed: {final_stats['failed']}")
    print()

    # Show processed news by symbol
    print("-" * 60)
    print("Processed News Stacks")
    print("-" * 60)

    # Get unique symbols from processed news
    symbols_query = """
    SELECT DISTINCT symbol
    FROM stock_news
    ORDER BY symbol
    """

    def _get_symbols():
        return supabase_client.rpc('exec_sql', {'sql': symbols_query}).execute()

    # Fallback: use common test symbols
    test_symbols = ["AAPL", "TSLA", "GOOGL"]

    for symbol in test_symbols:
        news_stack = await stock_news_db.get_news_stack(symbol=symbol, limit=5)
        if news_stack:
            print(f"\n{symbol} News Stack ({len(news_stack)} articles):")
            for article in news_stack:
                title = article.get('title', 'No title')[:60]
                position = article.get('position_in_stack', '?')
                print(f"   [{position}] {title}...")

    print()
    print("=" * 60)
    print("✅ PROCESSING COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
