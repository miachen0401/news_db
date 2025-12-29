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
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from fastapi import FastAPI, BackgroundTasks

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


# Load environment variables on startup
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

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
            "trigger_fetch": "POST /trigger/fetch",
            "trigger_recategorize": "POST /trigger/recategorize",
            "trigger_summary": "POST /trigger/summary",
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
            "POST /trigger/all"
        ]
    }


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


@app.post("/trigger/all")
async def trigger_all(background_tasks: BackgroundTasks):
    """Manually trigger all jobs"""
    logger.info("Manual trigger: All jobs")
    background_tasks.add_task(run_fetch_incremental)
    background_tasks.add_task(run_recategorize_existing)
    background_tasks.add_task(run_daily_summary)

    return {
        "status": "triggered",
        "jobs": ["fetch_incremental", "recategorize_existing", "daily_summary"],
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
