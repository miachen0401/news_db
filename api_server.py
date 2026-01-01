"""FastAPI server for manual news job triggering."""
# Add project root and api directory to path (must be first)
import sys
from pathlib import Path

# Get the project root directory (where api_server.py is located)
PROJECT_ROOT = Path(__file__).parent.resolve()
API_DIR = PROJECT_ROOT / "api"

# Add both project root (for api package) and api dir (for src module)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import os
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Import the main functions from your scripts
from api.fetch_incremental_llm_new import main as fetch_main
from api.generate_daily_summary import main as summary_main
from api.recategorize import main as recategorize_main
from api.generate_company_summary import generate_all_company_summaries

# Import for new GET endpoints
from supabase import create_client
from api.src.config import INCLUDED_CATEGORIES
from api.src.db.daily_highlights import DailyHighlightDB

# EST timezone
EST = timezone(timedelta(hours=-5))

# Track job execution status
job_status = {
    "fetch_incremental": {
        "last_run": None,
        "last_status": "never_run",
        "last_error": None
    },
    "recategorize_existing": {
        "last_run": None,
        "last_status": "never_run",
        "last_error": None
    },
    "daily_summary": {
        "last_run": None,
        "last_status": "never_run",
        "last_error": None
    },
    "company_summaries": {
        "last_run": None,
        "last_status": "never_run",
        "last_error": None
    }
}


async def run_fetch_incremental():
    """Wrapper function to run fetch_incremental_llm_new.py"""
    job_name = "fetch_incremental"
    try:
        logger.info("=" * 70)
        logger.info("SCHEDULED: Starting incremental news fetch")
        logger.info("=" * 70)

        await fetch_main()

        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "success"
        job_status[job_name]["last_error"] = None

        logger.info("SCHEDULED: Incremental fetch completed successfully")

    except Exception as e:
        logger.error(f"SCHEDULED: Error in incremental fetch: {e}")
        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "error"
        job_status[job_name]["last_error"] = str(e)


async def run_recategorize_existing():
    """Wrapper function to run recategorize_existing.py"""
    job_name = "recategorize_existing"
    try:
        logger.info("=" * 70)
        logger.info("SCHEDULED: Starting re-categorization service")
        logger.info("=" * 70)

        await recategorize_main()

        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "success"
        job_status[job_name]["last_error"] = None

        logger.info("SCHEDULED: Re-categorization completed successfully")

    except Exception as e:
        logger.error(f"SCHEDULED: Error in re-categorization: {e}")
        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "error"
        job_status[job_name]["last_error"] = str(e)


async def run_daily_summary():
    """Wrapper function to run generate_daily_summary.py"""
    job_name = "daily_summary"
    try:
        logger.info("=" * 70)
        logger.info("SCHEDULED: Starting daily summary generation")
        logger.info("=" * 70)

        await summary_main()

        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "success"
        job_status[job_name]["last_error"] = None

        logger.info("SCHEDULED: Daily summary completed successfully")

    except Exception as e:
        logger.error(f"SCHEDULED: Error in daily summary: {e}")
        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "error"
        job_status[job_name]["last_error"] = str(e)


async def run_company_summaries():
    """Wrapper function to run generate_company_summary.py for all companies"""
    job_name = "company_summaries"
    try:
        logger.info("=" * 70)
        logger.info("SCHEDULED: Starting company summaries generation")
        logger.info("=" * 70)

        await generate_all_company_summaries()

        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "success"
        job_status[job_name]["last_error"] = None

        logger.info("SCHEDULED: Company summaries completed successfully")

    except Exception as e:
        logger.error(f"SCHEDULED: Error in company summaries: {e}")
        job_status[job_name]["last_run"] = datetime.now(timezone.utc)
        job_status[job_name]["last_status"] = "error"
        job_status[job_name]["last_error"] = str(e)


# Load environment variables on startup
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Initialize Supabase client for GET endpoints
supabase_url = os.getenv("SUPABASE_NEWS_URL")
supabase_key = os.getenv("SUPABASE_NEWS_KEY")
supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None

# Initialize FastAPI app
app = FastAPI(
    title="News Fetcher & Summarizer API",
    description="Manual trigger API for news fetching and summarization",
    version="1.0.0"
)


@app.get("/")
async def root():
    """Health check endpoint"""
    now_utc = datetime.now(timezone.utc)
    now_est = now_utc.astimezone(EST)

    return {
        "status": "running",
        "service": "News Fetcher & Summarizer API",
        "mode": "manual_trigger",
        "current_time_utc": now_utc.isoformat(),
        "current_time_est": now_est.strftime("%Y-%m-%d %H:%M:%S EST"),
        "job_history": job_status,
        "endpoints": {
            "get_company_news": "GET /news/company/{symbols}",
            "get_daily_summary": "GET /summary/daily",
            "get_company_summary": "GET /summary/{symbol}",
            "trigger_fetch": "POST /trigger/fetch",
            "trigger_recategorize": "POST /trigger/recategorize",
            "trigger_summary": "POST /trigger/summary",
            "trigger_company_summaries": "POST /trigger/company-summaries",
            "trigger_all": "POST /trigger/all"
        }
    }


@app.get("/health")
async def health():
    """Simple health check for Render"""
    return {"status": "ok"}


@app.get("/status")
async def get_status():
    """Get job execution history"""
    return {
        "mode": "manual_trigger",
        "message": "Jobs are triggered via POST endpoints, not scheduled",
        "job_history": job_status,
        "available_triggers": [
            "POST /trigger/fetch",
            "POST /trigger/recategorize",
            "POST /trigger/summary",
            "POST /trigger/company-summaries",
            "POST /trigger/all"
        ]
    }


@app.get("/news/company/{symbols}")
async def get_company_news(symbols: str, limit: int = 10):
    """
    Get 10 most recent news for specific company symbol(s).

    Args:
        symbols: Company symbol(s), comma-separated (e.g., "AAPL" or "AAPL,TSLA,NVDA")

    Returns:
        JSON with list of news articles (summary and published_at in EST)
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Parse symbols (comma-separated)
    symbol_list = [s.strip().upper() for s in symbols.split(",")]

    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)

    try:
        # Query database for news matching any of the symbols
        # Filter by INCLUDED_CATEGORIES and get 10 most recent
        def _fetch_news():
            query = (
                supabase
                .table("stock_news")
                .select("title, summary, published_at, symbol, category, source, url")
                .in_("category", INCLUDED_CATEGORIES)
                .gte("published_at", three_days_ago.isoformat())
                .order("published_at", desc=True)
                #.limit(100)  # Get more to filter by symbol
            )
            return query.execute()

        result = await asyncio.to_thread(_fetch_news)
        news_items = result.data or []

        # Filter by symbol (check if any requested symbol appears in the news)
        filtered_news = []
        for item in news_items:
            item_symbol = item.get("symbol", "")
            # Check if any requested symbol is in the item's symbol field
            # (symbol field might contain comma-separated symbols)
            if any(symbol in item_symbol.upper() for symbol in symbol_list):
                filtered_news.append(item)
                if len(filtered_news) >= limit:
                    break

        # Convert published_at from UTC to EST
        for item in filtered_news:
            if item.get("published_at"):
                utc_time = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                est_time = utc_time.astimezone(EST)
                item["published_at"] = est_time.strftime("%Y-%m-%d %H:%M:%S EST")

        return JSONResponse(content={
            "symbols": symbol_list,
            "count": len(filtered_news),
            "news": filtered_news
        })

    except Exception as e:
        logger.error(f"Error fetching company news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary/daily")
async def get_daily_summary():
    """
    Get current daily summary (8 AM or 6 PM based on current time).
    If summary doesn't exist, generates it first.

    Returns:
        JSON with summary_date, summary_time, and summary text
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not configured")

    try:
        # Import determine_summary_target to find which summary we need
        from api.generate_daily_summary import determine_summary_target

        # Get current time in EST
        now_est = datetime.now(timezone.utc).astimezone(EST)

        # Determine which summary to check for
        summary_date_est, summary_time_est, _, _ = determine_summary_target(now_est)

        # Check if summary exists (symbol="general" for general summaries)
        highlights_db = DailyHighlightDB(client=supabase)
        existing = await highlights_db.get_highlight(
            summary_date=summary_date_est,
            summary_time=summary_time_est,
            symbol="general"
        )

        if existing:
            # Summary exists, return it
            return JSONResponse(content={
                "status": "found",
                "summary_date": existing.get("summary_date"),
                "summary_time": existing.get("summary_time"),
                "highlight_text": existing.get("highlight_text"),
                "news_count": existing.get("news_count"),
                "updated_at": existing.get("updated_at")
            })

        # Summary doesn't exist, generate it
        logger.info(f"Daily summary not found for {summary_date_est} {summary_time_est}, generating...")

        # Run generate_daily_summary
        await summary_main()

        # Try to fetch again after generation
        existing = await highlights_db.get_highlight(
            summary_date=summary_date_est,
            summary_time=summary_time_est,
            symbol="general"
        )

        if existing:
            return JSONResponse(content={
                "status": "generated",
                "summary_date": existing.get("summary_date"),
                "summary_time": existing.get("summary_time"),
                "highlight_text": existing.get("highlight_text"),
                "news_count": existing.get("news_count"),
                "updated_at": existing.get("updated_at")
            })
        else:
            # Still not found after generation
            raise HTTPException(
                status_code=500,
                detail="Daily summary not found after running generate summary"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting daily summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary/{symbol}")
async def get_company_summary(symbol: str):
    """
    Get current company-specific summary (8 AM or 6 PM based on current time).
    If summary doesn't exist, generates it first.

    Args:
        symbol: Company stock symbol (e.g., AAPL)

    Returns:
        JSON with company, summary_date, summary_time, and summary text
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Import companies list
    from api.src.companies import TRACKED_COMPANIES

    # Validate symbol
    symbol = symbol.upper()
    if symbol not in TRACKED_COMPANIES:
        raise HTTPException(
            status_code=404,
            detail=f"Company symbol '{symbol}' not found in tracked companies"
        )

    try:
        # Import determine_summary_target and generate_company_summary
        from api.generate_daily_summary import determine_summary_target
        from api.generate_company_summary import generate_company_summary

        # Get current time in EST
        now_est = datetime.now(timezone.utc).astimezone(EST)

        # Determine which summary to check for
        summary_date_est, summary_time_est, _, _ = determine_summary_target(now_est)

        # Check if company summary exists
        highlights_db = DailyHighlightDB(client=supabase)
        existing = await highlights_db.get_highlight(
            summary_date=summary_date_est,
            summary_time=summary_time_est,
            symbol=symbol
        )

        if existing:
            # Summary exists, return it
            return JSONResponse(content={
                "status": "found",
                "company": TRACKED_COMPANIES[symbol],
                "symbol": symbol,
                "summary_date": existing.get("summary_date"),
                "summary_time": existing.get("summary_time"),
                "highlight_text": existing.get("highlight_text"),
                "news_count": existing.get("news_count"),
                "updated_at": existing.get("updated_at")
            })

        # Summary doesn't exist, generate it
        logger.info(f"Company summary not found for {symbol} {summary_date_est} {summary_time_est}, generating...")

        # Generate company summary
        result = await generate_company_summary(symbol)

        # Try to fetch again after generation
        existing = await highlights_db.get_highlight(
            summary_date=summary_date_est,
            summary_time=summary_time_est,
            symbol=symbol
        )

        if existing:
            return JSONResponse(content={
                "status": "generated",
                "company": TRACKED_COMPANIES[symbol],
                "symbol": symbol,
                "summary_date": existing.get("summary_date"),
                "summary_time": existing.get("summary_time"),
                "highlight_text": existing.get("highlight_text"),
                "news_count": existing.get("news_count"),
                "updated_at": existing.get("updated_at")
            })
        else:
            # Still not found after generation (likely no news for this company)
            # Return the generated result directly
            if result:
                return JSONResponse(content={
                    "status": "generated",
                    "company": TRACKED_COMPANIES[symbol],
                    "symbol": symbol,
                    "summary_date": result.get("summary_date"),
                    "summary_time": result.get("summary_time"),
                    "highlight_text": result.get("highlight_text"),
                    "news_count": result.get("news_count")
                })
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Company summary not found after generation for {symbol}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting company summary for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trigger/fetch")
async def trigger_fetch(background_tasks: BackgroundTasks):
    """Manually trigger incremental news fetch"""
    logger.info("Manual trigger: Incremental fetch")
    background_tasks.add_task(run_fetch_incremental)

    return {
        "status": "triggered",
        "job": "fetch_incremental",
        "message": "Incremental fetch started in background"
    }


@app.post("/trigger/recategorize")
async def trigger_recategorize(background_tasks: BackgroundTasks):
    """Manually trigger re-categorization service"""
    logger.info("Manual trigger: Re-categorization")
    background_tasks.add_task(run_recategorize_existing)

    return {
        "status": "triggered",
        "job": "recategorize_existing",
        "message": "Re-categorization service started in background"
    }


@app.post("/trigger/summary")
async def trigger_summary(background_tasks: BackgroundTasks):
    """Manually trigger daily summary generation"""
    logger.info("Manual trigger: Daily summary")
    background_tasks.add_task(run_daily_summary)

    return {
        "status": "triggered",
        "job": "daily_summary",
        "message": "Daily summary generation started in background"
    }


@app.post("/trigger/company-summaries")
async def trigger_company_summaries(background_tasks: BackgroundTasks):
    """Manually trigger company summaries generation for all tracked companies"""
    logger.info("Manual trigger: Company summaries")
    background_tasks.add_task(run_company_summaries)

    return {
        "status": "triggered",
        "job": "company_summaries",
        "message": "Company summaries generation started in background"
    }


@app.post("/trigger/all")
async def trigger_all(background_tasks: BackgroundTasks):
    """Manually trigger all jobs"""
    logger.info("Manual trigger: All jobs")
    background_tasks.add_task(run_fetch_incremental)
    background_tasks.add_task(run_recategorize_existing)
    background_tasks.add_task(run_daily_summary)
    background_tasks.add_task(run_company_summaries)

    return {
        "status": "triggered",
        "jobs": ["fetch_incremental", "recategorize_existing", "daily_summary", "company_summaries"],
        "message": "All jobs started in background"
    }


if __name__ == "__main__":
    import uvicorn

    # Run the server
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=False
    )
