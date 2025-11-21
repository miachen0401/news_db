# News Database - LLM Categorization System

Automated general news fetching with LLM-based categorization for financial news analysis.

## Overview

The system provides a complete pipeline for:
1. **Fetching general market news** from multiple sources (Finnhub, Polygon)
2. **Storing raw data** in a data lake (stock_news_raw table)
3. **LLM categorization** using Zhipu AI GLM-4-flash (15 categories)
4. **Storing categorized news** in stock_news table (filters out NON_FINANCIAL)
5. **Incremental updates** based on actual news publication timestamps

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
- Multiple times per day for daily summaries

## Configuration

Edit `config.py` to adjust settings:

```python
# LLM Processing Configuration
LLM_CONFIG = {
    "batch_size": 10,              # Items per LLM API call
    "processing_limit": 20,        # Max items to process per run
    "temperature": 0.3,            # LLM consistency
}

# News Fetching Configuration
FETCH_CONFIG = {
    "polygon_limit": 100,          # Max articles from Polygon
    "finnhub_limit": 100,          # Finnhub article limit
    "buffer_minutes": 1,           # Overlap window
}
```

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
- Stores `published_at` (actual news time)
- Tracks processing status

### stock_news
- Production table with categorized news
- No LIFO stack (all news stored)
- `category` - Primary LLM category
- `secondary_category` - Stock symbols mentioned

### fetch_state
- Tracks last fetch timestamp per source
- Enables incremental fetching
- Records articles fetched/stored

## File Structure

```
news_db/
├── fetch_incremental_llm.py           # Production script
├── test_fetch_llm_for_new_databse.py  # Initial setup script
│
├── fetchers/
│   └── general_news_fetcher.py        # Finnhub + Polygon
│
├── processors/
│   └── llm_news_processor.py          # LLM categorization
│
├── services/
│   └── llm_categorizer.py             # Zhipu AI integration
│
├── db/
│   └── stock_news.py                  # Database operations
│
├── storage/
│   ├── raw_news_storage.py            # Raw data staging
│   └── fetch_state_manager.py         # Timestamp tracking
│
├── models/
│   └── raw_news.py                    # Data models
│
└── config.py                          # Configuration
```

## API Rate Limits

- **Finnhub**: ~100 articles per request (no date filtering)
- **Polygon**: 5 requests/min (free tier), date filtering supported
- **Zhipu AI**: 10 items per batch for categorization

## Monitoring

Check fetch status:

```sql
-- Last fetch times
SELECT * FROM fetch_state ORDER BY updated_at DESC;

-- Raw news pending processing
SELECT COUNT(*) FROM stock_news_raw WHERE processing_status = 'pending';

-- Category distribution
SELECT category, COUNT(*)
FROM stock_news
GROUP BY category
ORDER BY COUNT(*) DESC;
```

## Troubleshooting

### Duplicate News
- System tracks `published_at` (news time), not fetch time
- Finnhub: Client-side filtering
- Polygon: Server-side with full timestamp (YYYY-MM-DDTHH:MM:SSZ)

### Missing published_at
- Run `migration_add_and_backfill_published_at.sql`
- Backfills from `raw_json` for existing records

### LLM API Errors
- Check `ZHIPU_API_KEY` in `.env`
- Monitor rate limits (10 items/batch, ~1s delay)
- Failed items logged with `processing_status = 'failed'`

## Documentation

- `docs/CODE_CLEANUP_2025-11-22.md` - System migration details
- `docs/FIX_Database_Docs.md` - Database fixes and migrations
- `docs/RECORD_Change.md` - Complete change history
- `news_category.txt` - Full category definitions

## Recent Changes

**2025-11-22:**
- ✅ Migrated to LLM-based categorization (from symbol-specific)
- ✅ Removed LIFO stack (now stores all news)
- ✅ Added `published_at` tracking for proper incremental fetching
- ✅ Cleaned up ~1,500 lines of obsolete code
- ✅ Fixed duplicate news issue with timestamp-based filtering

## License

Internal project for financial news analysis.
