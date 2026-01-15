"""Generate daily news summary and save to daily_highlights table."""
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
from src.config import LLM_MODELS
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
# Set httpx logging to WARNING to suppress HTTP request logs
logging.getLogger("httpx").setLevel(logging.WARNING)

# EST timezone (UTC-5) - for user input/display only
EST = timezone(timedelta(hours=-5))
UTC = timezone.utc

def determine_summary_target(now_est: datetime) -> tuple[date, time, datetime, datetime]:
    """
    Determine which summary should be generated based on current time.

    Two summary points per day (EST):
    - 8 AM: Covers yesterday 6 PM to today 8 AM
    - 6 PM: Covers yesterday 6 PM to today 6 PM

    Logic:
    - If current time is 8 AM - 5:59 PM: Generate/check 8 AM summary for today
    - If current time is 6 PM - 7:59 AM: Generate/check 6 PM summary
      - 6 PM - 11:59 PM: Today's 6 PM summary
      - 12 AM - 7:59 AM: Yesterday's 6 PM summary

    Args:
        now_est: Current time in EST timezone

    Returns:
        Tuple of (summary_date, summary_time, from_time_est, to_time_est)
    """
    current_hour = now_est.hour

    # Determine which summary to generate
    if 8 <= current_hour <= 17:  # 8 AM to 5:59 PM
        # Generate 8 AM summary for today
        summary_date_est = now_est.date()
        summary_time_est = time(8, 0, 0)
        # News window: yesterday 6 PM to today 8 AM
        from_time_est = datetime.combine(summary_date_est - timedelta(days=1), time(18, 0, 0))
        to_time_est = datetime.combine(summary_date_est, time(8, 0, 0))

    elif 18 <= current_hour <= 23:  # 6 PM to 11:59 PM
        # Generate 6 PM summary for today
        summary_date_est = now_est.date()
        summary_time_est = time(18, 0, 0)
        # News window: yesterday 6 PM to today 6 PM
        from_time_est = datetime.combine(summary_date_est - timedelta(days=1), time(18, 0, 0))
        to_time_est = datetime.combine(summary_date_est, time(18, 0, 0))

    else:  # 0-7 (12 AM to 7:59 AM)
        # Generate 6 PM summary for yesterday
        summary_date_est = (now_est - timedelta(days=1)).date()
        summary_time_est = time(18, 0, 0)
        # News window: yesterday 6 PM to yesterday 6 PM (actually day before yesterday 6 PM to yesterday 6 PM)
        from_time_est = datetime.combine(summary_date_est - timedelta(days=1), time(18, 0, 0))
        to_time_est = datetime.combine(summary_date_est, time(18, 0, 0))

    return summary_date_est, summary_time_est, from_time_est, to_time_est


async def main():
    """Generate daily summary for stock news."""
    logger.info("=" * 70)
    logger.info("DAILY NEWS SUMMARY GENERATOR")
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
    summarizer = DailySummarizer(api_key=zhipu_api_key)
    highlights_db = DailyHighlightDB(client=supabase)

    # ========================================
    # Determine which summary to generate based on current time
    # ========================================
    summary_date_est, summary_time_est, from_time_est, to_time_est = determine_summary_target(now_est)

    logger.info(f"Target Summary: {summary_date_est} {summary_time_est} EST")
    logger.info(f"News Window: {from_time_est.strftime('%m/%d %H:%M')} - {to_time_est.strftime('%m/%d %H:%M')} EST")
    logger.debug("")

    # ========================================
    # Check if summary already exists
    # ========================================
    logger.debug("-" * 70)
    logger.info("Checking for Existing Summary")
    logger.debug("-" * 70)

    existing = await highlights_db.get_highlight(
        summary_date=summary_date_est,
        summary_time=summary_time_est
    )

    if existing:
        logger.info(f"✓ Summary already exists for {summary_date_est} {summary_time_est} EST")
        logger.info(f"   News count: {existing.get('news_count', 0)}")
        logger.info(f"   Summary length: {len(existing.get('highlight_text', ''))} characters")
        logger.info(f"   Last updated: {existing.get('updated_at', 'N/A')}")
        logger.debug("")

        # Display existing summary
        highlight_text = existing.get('highlight_text', '')
        logger.debug("=" * 70)
        logger.debug("Existing Summary (Preview):")
        logger.debug("=" * 70)
        preview = highlight_text[:500] + "..." if len(highlight_text) > 500 else highlight_text
        logger.debug(preview)
        logger.debug("=" * 70)
        logger.debug("")

        logger.info("=" * 70)
        logger.info("SUMMARY RETRIEVAL COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Status: Existing summary returned")
        logger.info(f"Date: {summary_date_est} (EST)")
        logger.info(f"Time: {summary_time_est} (EST)")
        logger.debug("")

        await summarizer.close()
        return existing

    logger.info(f"No existing summary found - will generate new one")
    logger.debug("")

    # ========================================
    # Convert EST to UTC for database queries
    # ========================================
    from_time = from_time_est.replace(tzinfo=EST).astimezone(UTC).replace(tzinfo=None)
    to_time = to_time_est.replace(tzinfo=EST).astimezone(UTC).replace(tzinfo=None)
    # ========================================
    # STEP 1: Fetch news from database (using UTC)
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 1: Fetch News from Database")
    logger.debug("-" * 70)
    try:
        def _fetch_news():
            return (
                supabase
                .table("stock_news")
                .select("id, title, summary, category, symbol, source, published_at")
                .gte("published_at", from_time.isoformat())
                .lte("published_at", to_time.isoformat())
                .in_("category", INCLUDED_CATEGORIES)  # Only include valid financial categories (whitelist)
                .order("published_at", desc=False)
                .execute()
            )

        result = await asyncio.to_thread(_fetch_news)
        news_items = result.data or []

        logger.info(f"Fetched {len(news_items)} news articles (only including {len(INCLUDED_CATEGORIES)} valid categories)")
        # Count by category
        category_counts = {}
        for item in news_items:
            cat = item.get('category', 'UNCATEGORIZED')
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if category_counts:
            logger.info(f"News by Category:")
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                logger.info(f"   {cat}: {count}")
        logger.debug("")
    except Exception as e:
        logger.info(f"Error fetching news: {e}")
        return

    # ========================================
    # STEP 2: Generate summary with LLM
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 2: Generate Daily Summary")
    logger.debug("-" * 70)
    if len(news_items) == 0:
        logger.info("No news found in time window")
        highlight_text = f"No significant news from {from_time_est.strftime('%m/%d %H:%M')} to {to_time_est.strftime('%m/%d %H:%M')} EST."
    else:
        model = LLM_MODELS['summarization']['model']
        logger.info(f"Generating summary using {model}...")
        highlight_text = await summarizer.generate_daily_summary(
            news_items=news_items,
            temperature=0.3
        )

        if not highlight_text:
            logger.info("Failed to generate summary")
            return

    logger.debug("")
    # ========================================
    # STEP 3: Save to Database
    # ========================================
    logger.debug("-" * 70)
    logger.info("STEP 3: Save to Database")
    logger.debug("-" * 70)
    categories_included = list(category_counts.keys()) if news_items else []

    success = await highlights_db.save_highlight(
        summary_date=summary_date_est,
        summary_time=summary_time_est,
        from_time=from_time,  # UTC timestamp
        to_time=to_time,      # UTC timestamp
        highlight_text=highlight_text,
        news_count=len(news_items),
        categories_included=categories_included,
        symbol="general"  # General market summary
    )

    if success:
        logger.info(f"Saved to database")
    else:
        logger.info(f"Failed to save to database")
    logger.debug("")
    # Cleanup
    await summarizer.close()

    logger.info("=" * 70)
    logger.info("DAILY SUMMARY COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Status: New summary generated")
    logger.info(f"Date: {summary_date_est} (EST)")
    logger.info(f"Time: {summary_time_est} (EST)")
    logger.info(f"News Count: {len(news_items)}")
    logger.info(f"Summary Length: {len(highlight_text)} characters")
    logger.debug("")

    return {
        "summary_date": summary_date_est.isoformat(),
        "summary_time": summary_time_est.isoformat(),
        "highlight_text": highlight_text,
        "news_count": len(news_items),
        "status": "generated"
    }
if __name__ == "__main__":
    asyncio.run(main())
