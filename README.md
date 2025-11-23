# News Database - LLM Categorization System

Automated general news fetching with LLM-based categorization for financial news analysis.

## Overview

The system provides a complete pipeline for:
1. **Fetching general market news** from multiple sources (Finnhub, Polygon)
2. **Storing raw data** in a data lake (stock_news_raw table)
3. **LLM categorization** using Zhipu AI GLM-4-flash (15 categories)
4. **Storing categorized news** in stock_news table (filters out NON_FINANCIAL)
5. **Incremental updates** based on actual news publication timestamps
6. **Daily summaries** - LLM-generated highlights stored in daily_highlights table

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

### Daily Summary Generation

Generate LLM-powered daily highlights from categorized news:

```bash
# Edit SUMMARY_DATE and SUMMARY_TIME in the file
# Default: current date/time
uv run python generate_daily_summary.py
```

This will:
- Fetch news from 6PM EST (previous day) to specified time
- Exclude `MACRO_NOBODY` category
- Generate structured summary using GLM-4.5-flash
- Store in `daily_highlights` table

**Configuration (edit in script):**
```python
SUMMARY_DATE = "2025-11-23"  # None = today, or "YYYY-MM-DD"
SUMMARY_TIME = "17:00:00"    # None = now, or "HH:MM:SS" (EST)
```

**📖 See [Daily Summary Guide](docs/DAILY_SUMMARY_GUIDE.md) for:**
- Complete usage instructions
- Time window calculation
- Programmatic access
- Monitoring queries

## Configuration

All system parameters are centralized in `config.py`. Edit this file to adjust behavior:

```python
# LLM Processing Configuration
LLM_CONFIG = {
    "batch_size": 10,              # Items per LLM API call (1-50)
    "processing_limit": 20,        # Max items to process per run (1-500)
    "temperature": 0.3,            # LLM consistency (0.0-1.0)
}

# News Fetching Configuration
FETCH_CONFIG = {
    "finnhub_categories": ['general', 'merger'],  # Finnhub categories
    "polygon_limit": 200,          # Max articles from Polygon (10-1000)
    "buffer_minutes": 1,           # Overlap window (0-10)
}
```

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

```
news_db/
├── fetch_incremental_llm.py           # Production: incremental news fetching
├── test_fetch_llm_for_new_databse.py  # Initial database setup
├── generate_daily_summary.py          # Generate daily highlights
│
├── fetchers/
│   └── general_news_fetcher.py        # Finnhub + Polygon API
│
├── processors/
│   └── llm_news_processor.py          # LLM categorization pipeline
│
├── services/
│   ├── llm_categorizer.py             # Zhipu AI categorization
│   └── daily_summarizer.py            # Zhipu AI daily summaries
│
├── db/
│   ├── stock_news.py                  # stock_news operations
│   └── daily_highlights.py            # daily_highlights operations
│
├── storage/
│   ├── raw_news_storage.py            # Raw data staging
│   └── fetch_state_manager.py         # Timestamp tracking
│
├── models/
│   └── raw_news.py                    # Data models
│
├── migrations/
│   ├── create_daily_highlights_table.sql  # Daily highlights schema
│   └── alter_add_finnhub_max_id.sql       # Add finnhub_max_id column
│
├── docs/
│   ├── DAILY_SUMMARY_GUIDE.md         # Daily summary documentation
│   └── CONFIGURATION_GUIDE.md         # Configuration reference
│
└── config.py                          # Central configuration
```

## API Rate Limits

- **Finnhub**: ~100 articles per request, uses `minId` for incremental fetching
- **Polygon**: 5 requests/min (free tier), date filtering supported
- **Zhipu AI**:
  - GLM-4-flash: Categorization (10 items per batch)
  - GLM-4.5-flash: Daily summaries (handles large context)

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

- **[Daily Summary Guide](docs/DAILY_SUMMARY_GUIDE.md)** - Daily highlights feature
- **[Configuration Guide](docs/CONFIGURATION_GUIDE.md)** - System configuration
- `docs/CODE_CLEANUP_2025-11-22.md` - System migration details
- `docs/FIX_Database_Docs.md` - Database fixes and migrations
- `docs/RECORD_Change.md` - Complete change history
- `news_category.txt` - Full category definitions
- `daliysummary.txt` - Daily summary requirements

## Recent Changes

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
