"""Generate daily news summary and save to daily_highlights table."""
import asyncio
import os
from pathlib import Path
from datetime import datetime, date, time, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client

from services.daily_summarizer import DailySummarizer
from db.daily_highlights import DailyHighlightDB

# EST timezone (UTC-5) - for user input/display only
EST = timezone(timedelta(hours=-5))
UTC = timezone.utc

# ============================================
# CONFIGURATION: Change these as needed
# ============================================
SUMMARY_DATE = "2025-11-23"  # None = today, or specify date like "2025-11-23"
SUMMARY_TIME = "07:00:00"  # None = now, or specify time like "17:00:00"


async def main():
    """Generate daily summary for stock news."""
    print("=" * 70)
    print("📊 DAILY NEWS SUMMARY GENERATOR")
    print("=" * 70)
    now_est = datetime.now(UTC).astimezone(EST)
    print(f"Run time: {now_est.strftime('%Y-%m-%d %H:%M:%S')} EST")
    print()

    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    zhipu_api_key = os.getenv("ZHIPU_API_KEY")
    supabase_url = os.getenv("SUPABASE_NEWS_URL")
    supabase_key = os.getenv("SUPABASE_NEWS_KEY")

    # Validate
    if not all([zhipu_api_key, supabase_url, supabase_key]):
        print("❌ Missing required environment variables")
        return

    print("✅ Configuration loaded")
    print()

    # Initialize clients
    supabase = create_client(supabase_url, supabase_key)
    summarizer = DailySummarizer(api_key=zhipu_api_key)
    highlights_db = DailyHighlightDB(client=supabase)

    # ========================================
    # Convert EST input to UTC (all processing uses UTC)
    # ========================================
    if SUMMARY_DATE:
        summary_date_est = datetime.strptime(SUMMARY_DATE, "%Y-%m-%d").date()
    else:
        summary_date_est = datetime.now(UTC).astimezone(EST).date()

    if SUMMARY_TIME:
        summary_time_est = datetime.strptime(SUMMARY_TIME, "%H:%M:%S").time()
    else:
        summary_time_est = datetime.now(UTC).astimezone(EST).time()

    # Convert EST to UTC for all processing
    # From: 6PM EST the day before
    from_date_est = summary_date_est - timedelta(days=1)
    from_time_est = datetime.combine(from_date_est, time(18, 0, 0))
    from_time = from_time_est.replace(tzinfo=EST).astimezone(UTC).replace(tzinfo=None)

    # To: summary_time EST on summary_date
    to_time_est = datetime.combine(summary_date_est, summary_time_est)
    to_time = to_time_est.replace(tzinfo=EST).astimezone(UTC).replace(tzinfo=None)

    print(f"📅 Summary for: {summary_date_est} {summary_time_est} EST")
    print(f"📰 News window: {from_time_est.strftime('%m/%d %H:%M')} - {to_time_est.strftime('%m/%d %H:%M')} EST")
    print()

    # ========================================
    # STEP 1: Fetch news from database (using UTC)
    # ========================================
    print("-" * 70)
    print("STEP 1: Fetch News from Database")
    print("-" * 70)

    try:
        def _fetch_news():
            return (
                supabase
                .table("stock_news")
                .select("id, title, summary, category, secondary_category, source, published_at")
                .gte("published_at", from_time.isoformat())
                .lte("published_at", to_time.isoformat())
                .neq("category", "MACRO_NOBODY")  # Exclude MACRO_NOBODY
                .order("published_at", desc=False)
                .execute()
            )

        result = await asyncio.to_thread(_fetch_news)
        news_items = result.data or []

        print(f"📰 Fetched {len(news_items)} news articles (excluding MACRO_NOBODY)")

        # Count by category
        category_counts = {}
        for item in news_items:
            cat = item.get('category', 'UNCATEGORIZED')
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if category_counts:
            print(f"\n📊 News by Category:")
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
                print(f"   {cat}: {count}")

        print()

    except Exception as e:
        print(f"❌ Error fetching news: {e}")
        return

    # ========================================
    # STEP 2: Generate summary with LLM
    # ========================================
    print("-" * 70)
    print("STEP 2: Generate Daily Summary")
    print("-" * 70)

    if len(news_items) == 0:
        print("⚠️  No news found in time window")
        highlight_text = f"No significant news from {from_time_est.strftime('%m/%d %H:%M')} to {to_time_est.strftime('%m/%d %H:%M')} EST."
    else:
        print(f"🤖 Generating summary using GLM-4-flash...")
        highlight_text = await summarizer.generate_daily_summary(
            news_items=news_items,
            temperature=0.3
        )

        if not highlight_text:
            print("❌ Failed to generate summary")
            return

    print()
    print("=" * 70)
    print("Generated Summary:")
    print("=" * 70)
    print(highlight_text)
    print("=" * 70)
    print()

    # ========================================
    # STEP 3: Save to daily_highlights
    # ========================================
    print("-" * 70)
    print("STEP 3: Save to Database")
    print("-" * 70)

    categories_included = list(category_counts.keys()) if news_items else []

    success = await highlights_db.save_highlight(
        summary_date=summary_date_est,
        summary_time=summary_time_est,
        from_time=from_time,  # UTC timestamp
        to_time=to_time,      # UTC timestamp
        highlight_text=highlight_text,
        news_count=len(news_items),
        categories_included=categories_included
    )

    if success:
        print(f"✅ Saved to database")
    else:
        print(f"❌ Failed to save to database")

    print()

    # Cleanup
    await summarizer.close()

    print("=" * 70)
    print("✅ DAILY SUMMARY COMPLETE")
    print("=" * 70)
    print(f"📅 Date: {summary_date_est} (EST)")
    print(f"🕐 Time: {summary_time_est} (EST)")
    print(f"📰 News Count: {len(news_items)}")
    print(f"📝 Summary Length: {len(highlight_text)} characters")
    print()


if __name__ == "__main__":
    asyncio.run(main())
