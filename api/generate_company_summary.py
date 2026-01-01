"""Generate company-specific news summary and save to daily_highlights table."""
# Add api directory to path so src module can be found (must be first)
import sys
from pathlib import Path
_api_dir = str(Path(__file__).parent.resolve())
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

import asyncio
import os
from datetime import datetime, date, time, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client

from src.services.daily_summarizer import DailySummarizer
from src.db.daily_highlights import DailyHighlightDB
from src.config import INCLUDED_CATEGORIES
from src.companies import TRACKED_COMPANIES
import logging
logger = logging.getLogger(__name__)

# EST timezone (UTC-5)
EST = timezone(timedelta(hours=-5))
UTC = timezone.utc


async def generate_company_summary(symbol: str) -> dict:
    """
    Generate company-specific summary for a given symbol.

    Args:
        symbol: Stock symbol (e.g., 'AAPL')

    Returns:
        Dict with summary information
    """
    # Import determine_summary_target
    from generate_daily_summary import determine_summary_target

    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    zhipu_api_key = os.getenv("ZHIPU_API_KEY")
    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    if not all([zhipu_api_key, supabase_url, supabase_key]):
        logger.error("Missing required environment variables")
        return None

    # Initialize clients
    supabase = create_client(supabase_url, supabase_key)
    summarizer = DailySummarizer(api_key=zhipu_api_key)
    highlights_db = DailyHighlightDB(client=supabase)

    # Get current time and determine summary target
    now_est = datetime.now(UTC).astimezone(EST)
    summary_date_est, summary_time_est, from_time_est, to_time_est = determine_summary_target(now_est)

    logger.info(f"Generating summary for {symbol} ({TRACKED_COMPANIES[symbol]})")
    logger.info(f"Target Summary: {summary_date_est} {summary_time_est} EST")
    logger.info(f"News Window: {from_time_est.strftime('%m/%d %H:%M')} - {to_time_est.strftime('%m/%d %H:%M')} EST")

    # Convert EST to UTC for database queries
    from_time = from_time_est.replace(tzinfo=EST).astimezone(UTC).replace(tzinfo=None)
    to_time = to_time_est.replace(tzinfo=EST).astimezone(UTC).replace(tzinfo=None)

    # Fetch news for this company
    try:
        def _fetch_news():
            return (
                supabase
                .table("stock_news")
                .select("id, title, summary, category, symbol, source, published_at")
                .gte("published_at", from_time.isoformat())
                .lte("published_at", to_time.isoformat())
                .in_("category", INCLUDED_CATEGORIES)
                .order("published_at", desc=False)
                .execute()
            )

        result = await asyncio.to_thread(_fetch_news)
        all_news_items = result.data or []

        # Filter news for this specific company
        company_news = []
        for item in all_news_items:
            item_symbol = item.get('symbol', '')
            if symbol in item_symbol.upper():
                company_news.append(item)

        logger.info(f"Fetched {len(company_news)} news articles for {symbol}")

    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        await summarizer.close()
        return None

    # Generate summary
    if len(company_news) == 0:
        logger.info(f"No news found for {symbol} in time window")
        highlight_text = f"No news updates for {TRACKED_COMPANIES[symbol]} ({symbol}) during this period."
        news_count = 0
        categories_included = []
    else:
        logger.info(f"Generating company summary for {symbol}...")
        highlight_text = await summarizer.generate_company_summary(
            company_symbol=symbol,
            company_name=TRACKED_COMPANIES[symbol],
            news_items=company_news,
            temperature=0.3
        )

        if not highlight_text:
            logger.error(f"Failed to generate summary for {symbol}")
            await summarizer.close()
            return None

        news_count = len(company_news)

        # Count categories
        category_counts = {}
        for item in company_news:
            cat = item.get('category', 'UNCATEGORIZED')
            category_counts[cat] = category_counts.get(cat, 0) + 1
        categories_included = list(category_counts.keys())

    # Save to database
    success = await highlights_db.save_highlight(
        summary_date=summary_date_est,
        summary_time=summary_time_est,
        from_time=from_time,
        to_time=to_time,
        highlight_text=highlight_text,
        news_count=news_count,
        categories_included=categories_included,
        symbol=symbol
    )

    if success:
        logger.info(f"Saved company summary for {symbol} to database")
    else:
        logger.error(f"Failed to save company summary for {symbol} to database")

    # Cleanup
    await summarizer.close()

    return {
        "summary_date": summary_date_est.isoformat(),
        "summary_time": summary_time_est.isoformat(),
        "highlight_text": highlight_text,
        "news_count": news_count,
        "symbol": symbol,
        "status": "generated"
    }


async def generate_all_company_summaries():
    """Generate summaries for all tracked companies, skipping those that already exist."""
    logger.info("=" * 70)
    logger.info("GENERATING COMPANY-SPECIFIC SUMMARIES FOR ALL COMPANIES")
    logger.info("=" * 70)

    # Import determine_summary_target
    from generate_daily_summary import determine_summary_target

    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    if not all([supabase_url, supabase_key]):
        logger.error("Missing required environment variables")
        return

    # Initialize database client
    supabase = create_client(supabase_url, supabase_key)
    highlights_db = DailyHighlightDB(client=supabase)

    # Get current time and determine summary target
    now_est = datetime.now(UTC).astimezone(EST)
    summary_date_est, summary_time_est, _, _ = determine_summary_target(now_est)

    logger.info(f"Target Summary: {summary_date_est} {summary_time_est} EST")
    logger.info(f"Total companies: {len(TRACKED_COMPANIES)}")
    logger.info("")

    # Track statistics
    skipped_count = 0
    generated_count = 0
    failed_count = 0

    for symbol in TRACKED_COMPANIES.keys():
        try:
            # Check if summary already exists
            existing = await highlights_db.get_highlight(
                summary_date=summary_date_est,
                summary_time=summary_time_est,
                symbol=symbol
            )

            if existing:
                logger.info(f"✓ Skipping {symbol} - summary already exists")
                skipped_count += 1
                continue

            # Generate summary
            logger.info(f"Generating summary for {symbol}...")
            await generate_company_summary(symbol)
            generated_count += 1

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            failed_count += 1

    logger.info("")
    logger.info("=" * 70)
    logger.info("COMPLETED ALL COMPANY SUMMARIES")
    logger.info("=" * 70)
    logger.info(f"Skipped (already exist): {skipped_count}")
    logger.info(f"Generated: {generated_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Total processed: {skipped_count + generated_count + failed_count}/{len(TRACKED_COMPANIES)}")
    logger.info("")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate company-specific news summary")
    parser.add_argument("--symbol", type=str, help="Company symbol (e.g., AAPL)")
    parser.add_argument("--all", action="store_true", help="Generate summaries for all companies")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.all:
        asyncio.run(generate_all_company_summaries())
    elif args.symbol:
        symbol = args.symbol.upper()
        if symbol not in TRACKED_COMPANIES:
            logger.error(f"Symbol {symbol} not found in tracked companies")
            sys.exit(1)
        asyncio.run(generate_company_summary(symbol))
    else:
        parser.print_help()
