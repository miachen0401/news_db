# News Database - LLM Categorization System

Automated general news fetching with LLM-based categorization for financial news analysis.

## Overview

The system provides a complete pipeline for:
1. **Fetching general market news** from multiple sources (Finnhub, Polygon)
2. **Fetching company-specific news** for tracked companies (Finnhub /company-news API)
3. **Storing raw data** in a data lake (stock_news_raw table)
4. **LLM categorization** using Zhipu AI GLM-4-flash (15 categories)
5. **Storing categorized news** in stock_news table (filters out NON_FINANCIAL)
6. **Incremental updates** based on actual news publication timestamps
7. **Daily summaries** - LLM-generated highlights stored in daily_highlights table

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  LLM-Based News Pipeline                     │
└─────────────────────────────────────────────────────────────┘

1. FETCH (General Market News)
   ├─ Finnhub API (general news, no symbol filter)
   │  └─ Client-side filtering by timestamp
   └─ Polygon API (general news with date range)
      └─ Server-side filtering by timestamp

2. STORE RAW (Data Lake)
   └─ stock_news_raw table
      ├─ raw_json (API responses)
      ├─ published_at (actual news publish time)
      ├─ fetch_source (finnhub, polygon)
      └─ processing_status (pending/completed/failed)

3. LLM CATEGORIZATION (Zhipu AI GLM-4-flash)
   ├─ 15 categories (MACRO_ECONOMIC, EARNINGS_FINANCIALS, etc.)
   ├─ Primary category (main news type)
   ├─ Secondary category (stock symbols mentioned)
   └─ Filter NON_FINANCIAL news

4. STORE CATEGORIZED (Production Data)
   └─ stock_news table
      ├─ All financial news stored (no LIFO stack)
      ├─ category (primary classification)
      ├─ secondary_category (stock symbols)
      └─ Ready for downstream analysis

5. INCREMENTAL UPDATES
   └─ Timestamp-based fetching
      ├─ Tracks latest news published_at per source
      ├─ 1-minute overlap buffer (avoid gaps)
      └─ No duplicate fetching
```

## Setup

### 1. Install Dependencies

```bash
# Using UV package manager
uv sync
```

### 2. Environment Variables

Create a `.env` file:

```bash
# Supabase
SUPABASE_NEWS_URL=your_supabase_url
SUPABASE_NEWS_KEY=your_supabase_key

# News APIs
FINNHUB_API_KEY=your_finnhub_key
MASSIVE_API_KEY=your_polygon_key  # Polygon.io

# LLM API
ZHIPU_API_KEY=your_zhipu_key  # Zhipu AI for categorization
```

### 3. Database Schema

Run migrations in Supabase SQL Editor:

```bash
# Initial schema
cat schema.sql
cat schema_stock_news.sql
cat schema_fetch_state.sql

# Add published_at column to raw table
cat migration_add_and_backfill_published_at.sql

# Add secondary_category for stock symbols
cat alter_add_secondary_category.sql
```

## Usage

### Initial Database Setup

For a **new/empty database**, use this script to fetch news from a specific date:

```bash
# Edit TARGET_DATE in the file (default: 2025-11-22)
uv run python test_fetch_llm_for_new_databse.py
```

This will:
- Fetch all news from the target date
- Categorize with LLM
- Store in database
- Record timestamp for incremental fetching

### Production: Incremental Fetching

For **ongoing updates**, use the incremental fetcher:

```bash
uv run python fetch_incremental_llm.py
```

Run this regularly (every 15-30 minutes or hourly). It will:
- Fetch only new news (after last timestamp)
- Categorize with LLM (batches of 20)
- Store financial news (skip NON_FINANCIAL)
- Update timestamp for next run

**Recommended Schedule:**
- Every 15-30 minutes for real-time updates
- Every 1 hour for moderate freshness
- Run daily summaries after market hours

### Data Corrections

The system automatically runs data corrections after LLM categorization to clean up malformed data:

```bash
# Automatic: Runs as STEP 6.5 in fetch_incremental_llm_new.py
# Manual: Run corrections standalone
uv run python run_data_corrections.py
```

**Current Corrections:**
- **Empty String Cleanup**: Converts "empty string" text to NULL/empty in `symbol` and `secondary_category` columns
- Runs automatically after each fetch to maintain data quality

### Daily Summary Generation

Generate LLM-powered daily highlights from categorized news:

```bash
# Edit SUMMARY_DATE and SUMMARY_TIME in the file
# Default: current date/time
uv run python generate_daily_summary.py
```

This will:
- Fetch news from 6PM EST (previous day) to specified time
- Include only valid financial categories (whitelist: 13 categories)
- Excludes: `MACRO_NOBODY`, `UNCATEGORIZED`, `ERROR`, `NON_FINANCIAL`
- Generate structured summary using GLM-4-flash
- **Save to local cache**: `.log/summary_YYYY-MM-DD_HH-MM-SS.log`
- Store in `daily_highlights` table

**Configuration (edit in script):**
```python
SUMMARY_DATE = "2025-11-23"  # None = today, or "YYYY-MM-DD"
SUMMARY_TIME = "17:00:00"    # None = now, or "HH:MM:SS" (EST)
```

**Log File Cache:**
- All summaries saved to `.log/` directory with timestamp
- Format: `summary_YYYY-MM-DD_HH-MM-SS.log`
- Includes metadata (date, news count, categories) and full summary text
- Terminal shows only 500-character preview
- Useful for local caching when deployed

**📖 See [Daily Summary Guide](docs/DAILY_SUMMARY_GUIDE.md) for:**
- Complete usage instructions
- Time window calculation
- Programmatic access
- Monitoring queries

## Configuration

All system parameters are centralized in `src/config.py`. Edit this file to adjust behavior:

```python
# LLM Model Configuration
LLM_MODELS = {
    "categorization": {
        "model": "glm-4-flash",           # Zhipu AI model
        "temperature": 0.3,               # Lower = more consistent
        "timeout": 60.0,                  # Request timeout (seconds)
        "max_retries": 2,                 # Retry on failure
        "concurrency_limit": 1,           # Max concurrent API calls
        "delay_between_batches": 2.0,     # Delay between batches (seconds)
    },
    "summarization": {
        "model": "glm-4-flash",           # Model for daily summaries
        "temperature": 0.3,
        "timeout": 120.0,
        "max_retries": 2,
    }
}

# LLM Processing Configuration
LLM_CONFIG = {
    "batch_size": 5,               # Items per LLM API call (reduced for rate limits)
    "processing_limit": 20,        # Max items to process per run
}

# News Fetching Configuration
FETCH_CONFIG = {
    "finnhub_categories": ['general', 'merger'],  # Finnhub categories
    "polygon_limit": 200,          # Max articles from Polygon (10-1000)
    "buffer_minutes": 1,           # Overlap window (0-10)
}

# Company-specific news tracking (Finnhub /company-news API)
TRACKED_COMPANIES = {
    "AAPL": "Apple Inc.",
    "TSLA": "Tesla Inc.",
    "NVDA": "NVIDIA Corporation",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "META": "Meta Platforms Inc.",
}

COMPANY_NEWS_CONFIG = {
    "enabled": True,               # Enable/disable company news fetching
    "limit": 50,                   # Max news per company per fetch
    "buffer_minutes": 1,           # Overlap window for incremental fetching
}

# Categories to include in daily summaries (whitelist approach)
INCLUDED_CATEGORIES = [
    "MACRO_ECONOMIC",           # Macroeconomic indicators
    "CENTRAL_BANK_POLICY",      # Monetary policy, interest rates
    "GEOPOLITICAL_SPECIFIC",    # Geopolitical news with named entities
    "INDUSTRY_REGULATION",      # Regulatory news for specific sectors
    "EARNINGS_FINANCIALS",      # Earnings, revenue, financial statements
    "CORPORATE_ACTIONS",        # M&A, stock splits, buybacks
    "MANAGEMENT_CHANGES",       # CEO, CFO, board changes
    "PRODUCT_TECH_UPDATE",      # New products, R&D, launches
    "BUSINESS_OPERATIONS",      # Supply chain, contracts, partnerships
    "ACCIDENT_INCIDENT",        # Breaches, accidents, recalls, lawsuits
    "ANALYST_RATING",           # Analyst upgrades/downgrades
    "MARKET_SENTIMENT",         # Investor sentiment, market flows
    "COMMODITY_FOREX_CRYPTO",   # Commodities, forex, crypto
]
```

**Key Settings:**
- `concurrency_limit`: Prevents 429 rate limit errors (GLM-4-flash free tier: 2 concurrent requests)
- `delay_between_batches`: Adds delay between batches to avoid hitting rate limits
- `max_retries`: Automatically retries failed API calls with exponential backoff
- `batch_size`: Reduced from 10 to 5 to avoid overwhelming the API
- `INCLUDED_CATEGORIES`: Only these 13 categories included in summaries (whitelist)

**📖 See [Configuration Guide](docs/CONFIGURATION_GUIDE.md) for:**
- Detailed parameter explanations
- Configuration scenarios (high-frequency, batch, testing)
- Best practices and troubleshooting
- Monitoring queries

## LLM Categories

The system uses 15 categories:

1. **MACRO_ECONOMIC** - Macroeconomic indicators
2. **CENTRAL_BANK_POLICY** - Monetary policy, interest rates
3. **MACRO_NOBODY** - Geopolitical commentary (no specific leaders)
4. **GEOPOLITICAL_SPECIFIC** - Named countries/leaders/governments
5. **INDUSTRY_REGULATION** - Regulatory news for specific sectors
6. **EARNINGS_FINANCIALS** - Earnings, revenue, financial statements
7. **CORPORATE_ACTIONS** - M&A, stock splits, buybacks
8. **MANAGEMENT_CHANGES** - CEO, CFO, board changes
9. **PRODUCT_TECH_UPDATE** - New products, R&D, launches
10. **BUSINESS_OPERATIONS** - Supply chain, contracts, partnerships
11. **ACCIDENT_INCIDENT** - Breaches, accidents, recalls, lawsuits
12. **ANALYST_RATING** - Analyst upgrades/downgrades
13. **MARKET_SENTIMENT** - Investor sentiment, market flows
14. **COMMODITY_FOREX_CRYPTO** - Commodities, forex, crypto
15. **NON_FINANCIAL** - Non-market news (filtered out)

## Database Tables

### stock_news_raw
- Staging area for raw API responses
- Stores `published_at` (actual news time in UTC)
- Tracks processing status

### stock_news
- Production table with categorized news
- No LIFO stack (all news stored)
- `category` - Primary LLM category
- `secondary_category` - Stock symbols mentioned
- `published_at` - News timestamp (UTC)

### fetch_state
- Tracks last fetch timestamp per source (UTC)
- Stores `finnhub_max_id` for incremental fetching
- Records articles fetched/stored

### daily_highlights
- Historical daily summaries
- `summary_date` / `summary_time` - When summary was generated (EST)
- `from_time` / `to_time` - News window (UTC)
- `highlight_text` - LLM-generated summary
- `news_count` - Number of articles summarized
- `categories_included` - Categories in the summary

## File Structure

The project is organized into several key directories:

```
news_db/
├── api/                               # FastAPI application
│   ├── fetch_incremental_llm_new.py   # Incremental news fetching
│   ├── generate_daily_summary.py      # Daily summary generation
│   ├── recategorize.py                # Re-categorization pipeline
│   └── src/                           # Core application code
│       ├── config.py                  # Central configuration
│       ├── companies.py               # Company watchlist
│       ├── fetchers/                  # News API fetchers
│       ├── processors/                # LLM processing pipelines
│       ├── services/                  # Business logic (LLM categorizer, summarizer)
│       ├── db/                        # Database operations
│       ├── storage/                   # Storage layer (raw news, state)
│       ├── models/                    # Data models
│       └── utils/                     # Utilities
│
├── api_server.py                      # FastAPI server entry point
├── trigger_remote.py                  # Remote API trigger script
│
├── docs/                              # Documentation
│   ├── PROJECT_STRUCTURE.txt          # Complete project structure
│   ├── QUICK_API_REFERENCE.md         # API endpoints reference
│   ├── DEPLOYMENT.md                  # Deployment guide
│   ├── RECORD_Change.md               # Change history
│   └── drafts/                        # Draft documentation
│
├── sql_query_archive/                 # SQL migrations
│   ├── schema*.sql                    # Database schemas
│   ├── alter*.sql                     # Schema alterations
│   └── create*.sql                    # Table creation scripts
│
├── tests/                             # Test suite
└── .log/                              # Local cache for summaries
```

**📖 See [Project Structure](docs/PROJECT_STRUCTURE.txt) for:**
- Complete directory tree with descriptions
- Database schema details
- Key configurations and workflows
- File naming conventions

## API Rate Limits

- **Finnhub**: ~100 articles per request, uses `minId` for incremental fetching
- **Polygon**: 5 requests/min (free tier), date filtering supported
- **Zhipu AI**:
  - GLM-4-flash: Free tier has 2 concurrent request limit
  - Concurrency control: System uses semaphore to limit to 1 concurrent request
  - Automatic retry: 429 errors trigger exponential backoff (5s, 10s, 15s)
  - Batch delay: 2s delay between batches to avoid rate limits
  - Categorization: 5 items per batch
  - Daily summaries: Handles large context with longer timeout (120s)

## Monitoring

### News Fetching

```sql
-- Last fetch times (per source)
SELECT
    symbol,
    fetch_source,
    last_fetch_to,
    finnhub_max_id,
    articles_fetched,
    updated_at
FROM fetch_state
ORDER BY updated_at DESC;

-- Raw news pending processing
SELECT COUNT(*) FROM stock_news_raw WHERE processing_status = 'pending';

-- Category distribution
SELECT category, COUNT(*)
FROM stock_news
GROUP BY category
ORDER BY COUNT(*) DESC;
```

### Daily Summaries

```sql
-- Recent summaries
SELECT
    summary_date,
    summary_time,
    news_count,
    array_length(categories_included, 1) as num_categories,
    length(highlight_text) as summary_length
FROM daily_highlights
ORDER BY summary_date DESC, summary_time DESC
LIMIT 10;

-- Summaries by date
SELECT
    summary_date,
    COUNT(*) as summaries_per_day,
    SUM(news_count) as total_news
FROM daily_highlights
GROUP BY summary_date
ORDER BY summary_date DESC;
```

## Troubleshooting

### Timezone Issues
- **All timestamps stored in UTC** in database (published_at, from_time, to_time)
- **User input/output in EST** (SUMMARY_DATE, SUMMARY_TIME, display logs)
- System automatically converts EST ↔ UTC
- If you see 5-hour time shift, check UTC vs EST handling

### Duplicate News
- Finnhub: Uses `minId` for incremental fetching (no duplicates)
- Polygon: Uses timestamp-based filtering with buffer
- Deduplication by URL in `stock_news_raw` table

### Missing published_at
- Run `migration_add_and_backfill_published_at.sql`
- Backfills from `raw_json` for existing records

### LLM API Errors
- Check `ZHIPU_API_KEY` in `.env`
- Monitor rate limits (10 items/batch for categorization)
- Failed items logged with `processing_status = 'failed'`

### Daily Summary Issues
- Ensure `daily_highlights` table exists (run migration)
- Check time window calculation (6PM EST previous day → summary time)
- Verify news exists in specified time range
- Check that `MACRO_NOBODY` category is being excluded

## Documentation

- **[Project Structure](docs/PROJECT_STRUCTURE.txt)** - Complete codebase structure and architecture
- **[Quick API Reference](docs/QUICK_API_REFERENCE.md)** - API endpoints and quick commands
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Render deployment instructions
- **[Change History](docs/RECORD_Change.md)** - Complete change log
- `docs/drafts/news_catogory.txt` - Full category definitions
- `docs/drafts/daliysummary.txt` - Daily summary requirements

## Recent Changes

**2025-11-29:**
- ✅ Added company-specific news tracking using Finnhub /company-news API
- ✅ Timestamp-based checkpoint tracking per company (same as polygon/finnhub)
- ✅ Configurable company list in `TRACKED_COMPANIES` (7 companies by default)
- ✅ Can enable/disable company news fetching via `COMPANY_NEWS_CONFIG['enabled']`
- ✅ Added local log file caching for daily summaries (`.log/` directory)
- ✅ Terminal now shows preview only, full summary cached locally
- ✅ Added data correction system (`DataCorrector` class)
- ✅ Automatic cleanup of "empty string" text in symbol/secondary_category columns
- ✅ Corrections run automatically after LLM categorization (STEP 6.5)

**2025-11-24:**
- ✅ Reorganized codebase - moved all production code to `src/` folder
- ✅ Updated all imports to use `src.` prefix for FastAPI integration
- ✅ Centralized configuration in `src/config.py`

**2025-11-23:**
- ✅ Added daily summary feature with GLM-4.5-flash
- ✅ Fixed critical timezone bug (UTC storage, EST display)
- ✅ Added `finnhub_max_id` for proper incremental fetching
- ✅ Updated to use `finnhub_{category}` source naming
- ✅ Created `daily_highlights` table for historical summaries

**2025-11-22:**
- ✅ Migrated to LLM-based categorization (from symbol-specific)
- ✅ Removed LIFO stack (now stores all news)
- ✅ Added `published_at` tracking for proper incremental fetching
- ✅ Cleaned up ~1,500 lines of obsolete code
- ✅ Fixed duplicate news issue with timestamp-based filtering

## License

Internal project for financial news analysis.
