# Change Records

## 2025-11-18 15:00: Refactored news_db from news_agent submodule to standalone repository
Created UV-based environment, removed backend dependencies, implemented standalone modules.

## 2025-11-18 15:30: Created migration scripts for existing stock_news table
Analyzed current schema and generated adjustment queries for LIFO stack compatibility.

## 2025-11-18 16:00: Fixed DROP INDEX error in migration script
Changed from DROP INDEX to ALTER TABLE DROP CONSTRAINT for constraint-backed index.

---

## Session 1: Initial Refactoring (2025-11-18)

### Files Created:
- `.gitignore` - Python project ignore rules
- `pyproject.toml` - UV project configuration
- `db/stock_news.py` - Standalone StockNewsDB class
- `schema_stock_news.sql` - Stock news table schema
- `SETUP.md` - Installation and setup guide

### Files Modified:
- `fetchers/finnhub_fetcher.py` - Removed backend imports, standalone FinnhubClient
- `processors/news_processor.py` - Uses local StockNewsDB
- `storage/raw_news_storage.py` - Absolute imports
- `test_fetch_news.py` - Local imports
- All `__init__.py` files - Absolute imports
- `README.md` - Updated usage examples

### Key Changes:
- Replaced `backend.app.*` imports → standalone implementations
- Relative imports → absolute imports
- Created LIFO stack implementation in StockNewsDB
- Set up UV environment with all dependencies

### Test Result:
✅ Successfully fetched 60 articles from Finnhub and stored in Supabase

---

## Session 2: Schema Migration (2025-11-18)

### Files Created:
- `adjust_stock_news_table.sql` - Migration script for existing table
- `check_stock_news_schema.sql` - Schema inspection queries
- `docs/FIX_Database_Docs.md` - Database fix documentation
- `docs/RECORD_Change.md` - This file

### Schema Analysis:
- Current table has 11 columns, needs 4 more
- Has `position_in_stack` (critical for LIFO)
- Missing: source_id, external_id, metadata, updated_at
- Index issue: UNIQUE on url (should be symbol+url)

### Fix Applied:
- Changed `DROP INDEX` → `ALTER TABLE DROP CONSTRAINT` (line 64)
- Properly handles constraint-backed unique index

## 2025-11-18 16:15: Investigated processing limit and failures
Test script only processes 10 items at a time; created test_process_all.py to handle all pending items.

### Issue Identified:
- `test_fetch_news.py` has `limit=10` on line 120
- Only first 10 pending items (all AAPL) were processed
- TSLA and GOOGL remain unprocessed (pending)
- 10 items failed processing (need to check error_log)

### Files Created:
- `check_failed_items.sql` - Query to check failed processing errors
- `test_process_all.py` - Process all pending items in batches

### Next Steps:
1. Run `check_failed_items.sql` to see why 10 items failed
2. Run `test_process_all.py` to process remaining items

## 2025-11-18 16:30: Added Polygon as second news source
Implemented PolygonNewsFetcher with full integration for fetching, storing, and processing news.

### Files Created:
- `fetchers/polygon_fetcher.py` - Polygon.io API client and fetcher
- `test_multi_source.py` - Test script for both Finnhub and Polygon

### Files Modified:
- `models/raw_news.py` - Added `from_polygon_response()` method
- `processors/news_processor.py` - Added `_process_polygon_json()` method
- `fetchers/__init__.py` - Export PolygonNewsFetcher

### Implementation Details:
- Polygon API endpoint: `/v2/reference/news`
- API key env var: `MASSIVE_API_KEY`
- Response format: ISO 8601 timestamps, different field names than Finnhub
- Rate limit handling: 200ms delay between requests (5 req/min free tier)
- Metadata stored: author, publisher, image_url, amp_url, tickers list

### Usage:
```bash
uv run python test_multi_source.py
```

## 2025-11-18 16:45: Created today's news fetcher with configurable symbols
Added dynamic test script that fetches only today's news with configurable symbol list.

### Files Created:
- `test_today_news.py` - Fetch today's news only (dynamic date)
- `config.py` - Centralized configuration for symbols and fetch settings

### Features:
- **Dynamic date:** Always fetches from today (00:00:00 to current time)
- **Configurable symbols:** Edit `config.py` to change which symbols to fetch
- **Both sources:** Fetches from Finnhub and Polygon
- **Auto-process:** Processes all pending items automatically
- **Summary view:** Shows news stacks with source and publisher info

### Configuration:
Edit `config.py` to customize:
- `DEFAULT_SYMBOLS` - List of symbols to fetch
- `FETCH_CONFIG` - Fetch and processing settings
- Predefined lists: `TOP_STOCKS`, `TECH_STOCKS`

### Usage:
```bash
uv run python test_today_news.py
```

Runs daily to fetch latest news for configured symbols.

## 2025-11-18 17:00: Implemented incremental fetching with timestamp tracking
Created production-ready incremental fetching system to avoid re-fetching old news.

### Files Created:
- `schema_fetch_state.sql` - Tracks last fetch timestamp per symbol+source
- `storage/fetch_state_manager.py` - Manages fetch state and incremental windows
- `fetch_incremental.py` - Production incremental fetcher

### How It Works:
1. **First run:** Fetches last 7 days of news, stores timestamp
2. **Subsequent runs:** Fetches only from (last_timestamp - 1min) to now
3. **Buffer window:** 1-minute overlap prevents missing news
4. **Duplicate check:** Still active as safety net

### Key Features:
- **Timestamp tracking:** Per symbol+source combination
- **Automatic incremental:** No manual configuration needed
- **Buffer window:** Configurable overlap (default 1 minute)
- **Stale detection:** Find symbols that haven't been fetched recently
- **Reset capability:** Force full refresh when needed

### Database Schema:
- `fetch_state` table: Tracks last_fetch_from, last_fetch_to
- `v_fetch_state_status` view: Shows time since last fetch
- Unique constraint on (symbol, fetch_source)

### Production Benefits:
- **Efficiency:** Only fetch new news, not entire history
- **API savings:** Reduce API calls dramatically
- **Speed:** Faster execution (fewer items to check)
- **Scalability:** Can run frequently (every 5-15 minutes)

### Usage:
```bash
# Run schema first (one time)
cat schema_fetch_state.sql | supabase sql

# Run incremental fetch
uv run python fetch_incremental.py
```

### Performance:
- First run: ~7 days of news
- Subsequent runs: Only last few minutes/hours
- Duplicate checking: Still active but processes fewer items

## 2025-11-18 17:15: Changed first run to fetch last 24 hours instead of 7 days
Modified default fetch window for first run from 7 days to 1 day (yesterday only).

### Change:
- `fetch_state_manager.py` line 49: Changed from `timedelta(days=7)` to `timedelta(days=1)`
- First run now fetches last 24 hours instead of full week
- Reduces initial fetch volume while still getting recent news

## 2025-11-20 01:15: Added fetch_source column to track API source
Added separate column to distinguish between news source (publisher) and fetch source (API).

### Files Created:
- `alter_add_fetch_source.sql` - Adds fetch_source column to stock_news table

### Files Modified:
- `processors/news_processor.py` - Added fetch_source to processed_data (both Finnhub and Polygon)
- `db/stock_news.py` - Added fetch_source to news_item dict

### Column Distinction:
- **source**: News publisher (Reuters, Bloomberg, WSJ, etc.)
- **fetch_source**: API that fetched the news (finnhub, polygon, newsapi, etc.)

### Usage for Data Quality Analysis:
```sql
-- Compare news count by API source
SELECT fetch_source, COUNT(*) FROM stock_news GROUP BY fetch_source;

-- Compare duplicates by source
SELECT fetch_source, COUNT(DISTINCT url) as unique_urls, COUNT(*) as total
FROM stock_news GROUP BY fetch_source;

-- Find overlapping news from different APIs
SELECT url, array_agg(DISTINCT fetch_source) as sources, COUNT(*)
FROM stock_news
GROUP BY url
HAVING COUNT(DISTINCT fetch_source) > 1;
```

### Migration:
Run `alter_add_fetch_source.sql` in Supabase to add the column.

## 2025-11-20 02:00: Complete restructure - LLM categorization instead of symbol-based fetching
Major refactor: Switched from symbol-specific fetching to general news with LLM categorization.

### Files Created:
- `fetchers/general_news_fetcher.py` - Fetches all news without symbol filtering
- `services/llm_categorizer.py` - Zhipu AI GLM-4-flash categorization
- `services/__init__.py` - Services module init
- `processors/llm_news_processor.py` - LLM-based processor (no LIFO stack)
- `alter_add_secondary_category.sql` - Adds secondary_category column
- `test_friday_llm.py` - Friday (2025-11-21) test script

### Files Modified:
- `db/stock_news.py` - Added `insert_news()` method (no stack, direct insert)

### Major Changes:

#### 1. Fetching Strategy:
**Before:** Fetch news per symbol (AAPL, TSLA, etc.)
**After:** Fetch all general news, no symbol filtering

#### 2. Storage Strategy:
**Before:** LIFO stack (top 5 per symbol)
**After:** Direct insert, all news stored (except NON_FINANCIAL)

#### 3. Categorization:
**Before:** Manual category assignment
**After:** LLM categorization with 15 categories

#### 4. Symbol Association:
**Before:** Fetched per symbol
**After:** LLM extracts mentioned stocks in `secondary_category`

### Schema Changes:
- Added `secondary_category` column for stock ticker symbols
- `category` = Primary category (MACRO_ECONOMIC, EARNINGS_FINANCIALS, etc.)
- `secondary_category` = Stock symbols mentioned (AAPL, TSLA) or empty

### LLM Categorization:
- Model: Zhipu AI GLM-4-flash
- API key: ZHIPU_API_KEY
- Batch processing: 10 items per API call
- 15 categories (see news_category.txt)
- NON_FINANCIAL news filtered out automatically

### Test Workflow:
1. Fetch Friday (2025-11-21) news only
2. Store all in stock_news_raw
3. LLM categorizes each article
4. Store in stock_news (except NON_FINANCIAL)
5. Record timestamp for incremental fetching

### Usage:
```bash
# Run schema changes
cat alter_add_secondary_category.sql | supabase sql

# Test with Friday news
uv run python test_friday_llm.py
```

### Next Steps:
- Incremental fetching will work with GENERAL symbol
- LLM will categorize all new news
- Can query by primary category or secondary_category (stocks)

## 2025-11-22 01:00: Created incremental fetcher for LLM categorization system
Adapted fetch_incremental.py to work with new general news + LLM categorization system.

### Files Created:
- `fetch_incremental_llm.py` - Production incremental fetcher with LLM categorization

### Key Changes:
- Uses "GENERAL" symbol instead of specific stock symbols (AAPL, TSLA, etc.)
- Fetches all general news from both Finnhub and Polygon
- Processes incrementally based on last fetch_state timestamp
- LLM categorizes in batches (limit=20 per cycle)
- Automatically filters NON_FINANCIAL news
- Updates fetch_state after successful run for next incremental fetch

### Workflow:
1. Get last fetch time from fetch_state (with 1-min buffer)
2. Fetch incremental general news from Finnhub and Polygon
3. Store in stock_news_raw
4. Update fetch_state with new timestamps
5. Process with LLM categorization in batches
6. Store financial news in stock_news (skip NON_FINANCIAL)
7. Show recent categorized news sample

### Usage:
```bash
# Run incremental fetch (fetches news after last timestamp)
uv run python fetch_incremental_llm.py
```

### Integration with Friday Test:
- `test_friday_llm.py` establishes baseline (Friday 2025-11-21)
- `fetch_incremental_llm.py` fetches news after that timestamp
- Each run updates timestamp for next incremental fetch

## 2025-11-22 01:30: Fixed duplicate news issue - use actual news timestamp instead of fetch time
Fixed timestamp tracking to use actual latest news published_at instead of current time to avoid duplicates.

### Issue:
- Different news APIs return news with different timezone conventions
- Using `datetime.now()` as fetch window endpoint caused duplicates
- Same news fetched multiple times because publish time != fetch time

### Root Cause:
- Finnhub/Polygon may return news published hours ago
- `fetch_state.last_fetch_to` was set to current time, not actual news time
- Next run would re-fetch the same old news

### Fix:
**`storage/fetch_state_manager.py`:**
- Added `get_latest_news_timestamp()` method
- Queries `stock_news_raw` for latest `published_at` by source
- `get_last_fetch_time()` now uses actual news timestamp as baseline
- Fallback: uses `fetch_state` table, then 24h default

**`fetch_incremental_llm.py`:**
- Calculates actual latest news timestamp from fetched items:
  ```python
  finnhub_latest = max(item.published_at for item in finnhub_items)
  ```
- Updates `fetch_state` with actual news timestamp, not current time
- Shows both timestamps in summary for transparency

### Result:
- No more duplicate fetching of old news
- Incremental fetching based on actual news publish time
- Works correctly across different timezones
- Next run fetches only news published after latest fetched article
